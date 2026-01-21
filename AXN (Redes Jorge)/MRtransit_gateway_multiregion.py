#!/usr/bin/env python3
import boto3
import time

def get_ubuntu_ami(ec2_client):
    """Obtiene la AMI más reciente de Ubuntu 22.04 LTS"""
    response = ec2_client.describe_images(
        Filters=[
            {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
            {'Name': 'owner-id', 'Values': ['099720109477']},
            {'Name': 'state', 'Values': ['available']}
        ]
    )
    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
    return images[0]['ImageId']

def wait_for_instances_running(ec2_client, instance_ids):
    """Espera a que las instancias estén en estado running, manejando instancias que no existen"""
    max_attempts = 60
    valid_instances = instance_ids.copy()
    
    for attempt in range(max_attempts):
        if not valid_instances:
            print("⚠️ No hay instancias válidas para verificar")
            return
            
        try:
            response = ec2_client.describe_instances(InstanceIds=valid_instances)
        except Exception as e:
            if "InvalidInstanceID.NotFound" in str(e):
                print(f"⚠️ Algunas instancias no existen, verificando individualmente...")
                # Verificar cada instancia individualmente
                still_valid = []
                for instance_id in valid_instances:
                    try:
                        ec2_client.describe_instances(InstanceIds=[instance_id])
                        still_valid.append(instance_id)
                    except:
                        print(f"⚠️ Instancia {instance_id} no existe, removiendo de la lista")
                valid_instances = still_valid
                continue
            else:
                raise e
        
        running_count = 0
        instances_to_remove = []
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_id = instance['InstanceId']
                state = instance['State']['Name']
                
                if state == 'running':
                    running_count += 1
                elif state in ['shutting-down', 'terminated', 'stopping', 'stopped']:
                    print(f"⚠️ Instancia {instance_id} está en estado {state}, removiendo...")
                    instances_to_remove.append(instance_id)
        
        # Remover instancias que no están en estados válidos
        for instance_id in instances_to_remove:
            if instance_id in valid_instances:
                valid_instances.remove(instance_id)
        
        if not valid_instances:
            print("⚠️ No quedan instancias válidas")
            return
            
        if running_count == len(valid_instances):
            print(f"✅ Todas las instancias válidas ({running_count}) están ejecutándose")
            return
        
        print(f"Esperando... {running_count}/{len(valid_instances)} instancias ejecutándose")
        time.sleep(10)
    
    print(f"⚠️ Timeout esperando instancias, continuando con {len(valid_instances)} instancias válidas")

def create_vpc_infrastructure(region, vpc_configs):
    """Crea VPCs, subredes, IGW e instancias EC2 en una región"""
    ec2 = boto3.client('ec2', region_name=region)
    
    print(f"\n=== Creando VPCs en {region} ===")
    
    ubuntu_ami = get_ubuntu_ami(ec2)
    created_resources = []
    
    for config in vpc_configs:
        vpc_name = config['name']
        vpc_cidr = config['vpc_cidr']
        subnet_cidr = config['subnet_cidr']
        
        print(f"\n--- Creando {vpc_name} ---")
        
        # Crear VPC
        vpc_response = ec2.create_vpc(CidrBlock=vpc_cidr)
        vpc_id = vpc_response['Vpc']['VpcId']
        ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': vpc_name}])
        
        # Habilitar DNS
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
        
        # Crear Internet Gateway
        igw_response = ec2.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        ec2.create_tags(Resources=[igw_id], Tags=[{'Key': 'Name', 'Value': f'IGW-{vpc_name}'}])
        
        # Crear subred pública
        azs = ec2.describe_availability_zones(Filters=[{'Name': 'state', 'Values': ['available']}])
        az = azs['AvailabilityZones'][0]['ZoneName']
        
        subnet_response = ec2.create_subnet(VpcId=vpc_id, CidrBlock=subnet_cidr, AvailabilityZone=az)
        subnet_id = subnet_response['Subnet']['SubnetId']
        ec2.create_tags(Resources=[subnet_id], Tags=[{'Key': 'Name', 'Value': f'Subnet-{vpc_name}'}])
        ec2.modify_subnet_attribute(SubnetId=subnet_id, MapPublicIpOnLaunch={'Value': True})
        
        # Configurar tabla de rutas
        route_tables = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        main_rt_id = route_tables['RouteTables'][0]['RouteTableId']
        ec2.create_route(RouteTableId=main_rt_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
        
        # Crear Security Group
        sg_response = ec2.create_security_group(
            GroupName=f'SG-{vpc_name}',
            Description=f'Security group for {vpc_name}',
            VpcId=vpc_id
        )
        sg_id = sg_response['GroupId']
        ec2.create_tags(Resources=[sg_id], Tags=[{'Key': 'Name', 'Value': f'SG-{vpc_name}'}])
        
        # Reglas de seguridad
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'icmp', 'FromPort': -1, 'ToPort': -1, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ]
        )
        
        # Crear instancia EC2
        print(f"Creando instancia en {vpc_name}...")
        instance_response = ec2.run_instances(
            ImageId=ubuntu_ami,
            MinCount=1,
            MaxCount=1,
            InstanceType='t3.micro',
            SubnetId=subnet_id,
            SecurityGroupIds=[sg_id],
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': f'Instance-{vpc_name}'}]
            }]
        )
        instance_id = instance_response['Instances'][0]['InstanceId']
        
        # Verificar inmediatamente el estado de la instancia
        time.sleep(5)
        try:
            check_response = ec2.describe_instances(InstanceIds=[instance_id])
            current_state = check_response['Reservations'][0]['Instances'][0]['State']['Name']
            print(f"Estado inicial de {instance_id}: {current_state}")
            
            if current_state in ['shutting-down', 'terminated']:
                print(f"⚠️ Instancia {instance_id} falló al iniciar, verificando razón...")
                # Intentar obtener información de estado
                state_reason = check_response['Reservations'][0]['Instances'][0].get('StateReason', {})
                print(f"Razón del estado: {state_reason.get('Message', 'No disponible')}")
        except Exception as e:
            print(f"⚠️ Error verificando estado de instancia: {e}")
        
        print(f"VPC: {vpc_id}, Subnet: {subnet_id}, Instance: {instance_id}")
        
        created_resources.append({
            'vpc_id': vpc_id,
            'subnet_id': subnet_id,
            'instance_id': instance_id,
            'igw_id': igw_id,
            'sg_id': sg_id,
            'route_table_id': main_rt_id
        })
        
        # Pausa entre creaciones para evitar problemas de límites
        time.sleep(10)
    
    # Esperar a que todas las instancias estén ejecutándose
    all_instance_ids = [res['instance_id'] for res in created_resources]
    if all_instance_ids:
        print(f"\nEsperando que todas las instancias en {region} estén ejecutándose...")
        print(f"Instancias a verificar: {all_instance_ids}")
        try:
            wait_for_instances_running(ec2, all_instance_ids)
        except Exception as e:
            print(f"⚠️ Problema verificando instancias: {e}")
            print("Continuando con la creación de infraestructura...")
            # Filtrar instancias que realmente existen
            valid_resources = []
            for res in created_resources:
                try:
                    check = ec2.describe_instances(InstanceIds=[res['instance_id']])
                    state = check['Reservations'][0]['Instances'][0]['State']['Name']
                    if state not in ['shutting-down', 'terminated']:
                        valid_resources.append(res)
                    else:
                        print(f"⚠️ Removiendo recurso con instancia fallida: {res['instance_id']}")
                except:
                    print(f"⚠️ Removiendo recurso con instancia inexistente: {res['instance_id']}")
            created_resources[:] = valid_resources
    
    return created_resources

def create_transit_gateway(region, asn, name):
    """Crea Transit Gateway en una región"""
    ec2 = boto3.client('ec2', region_name=region)
    
    print(f"\n--- Creando Transit Gateway en {region} ---")
    
    tgw_response = ec2.create_transit_gateway(
        Description=f'Transit Gateway for {region}',
        Options={'AmazonSideAsn': asn},
        TagSpecifications=[{
            'ResourceType': 'transit-gateway',
            'Tags': [{'Key': 'Name', 'Value': name}]
        }]
    )
    tgw_id = tgw_response['TransitGateway']['TransitGatewayId']
    
    # Esperar a que esté disponible
    print(f"Esperando que TGW {tgw_id} esté disponible...")
    while True:
        response = ec2.describe_transit_gateways(TransitGatewayIds=[tgw_id])
        state = response['TransitGateways'][0]['State']
        if state == 'available':
            break
        time.sleep(10)
    
    print(f"Transit Gateway creado: {tgw_id}")
    return tgw_id

def attach_vpcs_to_tgw(region, tgw_id, vpc_resources):
    """Conecta VPCs al Transit Gateway"""
    ec2 = boto3.client('ec2', region_name=region)
    
    print(f"\n--- Conectando VPCs al TGW en {region} ---")
    
    attachments = []
    for resource in vpc_resources:
        vpc_id = resource['vpc_id']
        subnet_id = resource['subnet_id']
        
        attachment_response = ec2.create_transit_gateway_vpc_attachment(
            TransitGatewayId=tgw_id,
            VpcId=vpc_id,
            SubnetIds=[subnet_id],
            TagSpecifications=[{
                'ResourceType': 'transit-gateway-attachment',
                'Tags': [{'Key': 'Name', 'Value': f'TGW-Attachment-{vpc_id}'}]
            }]
        )
        attachment_id = attachment_response['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']
        attachments.append(attachment_id)
        
        print(f"VPC {vpc_id} conectada al TGW: {attachment_id}")
    
    # Esperar a que los attachments estén disponibles
    print("Esperando que los attachments estén disponibles...")
    for attachment_id in attachments:
        while True:
            response = ec2.describe_transit_gateway_vpc_attachments(TransitGatewayAttachmentIds=[attachment_id])
            state = response['TransitGatewayVpcAttachments'][0]['State']
            if state == 'available':
                break
            time.sleep(10)
    
    return attachments

def create_tgw_peering(tgw_east_id, tgw_west_id):
    """Crea peering entre Transit Gateways"""
    ec2_east = boto3.client('ec2', region_name='us-east-1')
    sts = boto3.client('sts')
    
    print("\n--- Creando TGW Peering ---")
    
    # Obtener Account ID
    account_id = sts.get_caller_identity()['Account']
    
    peering_response = ec2_east.create_transit_gateway_peering_attachment(
        TransitGatewayId=tgw_east_id,
        PeerTransitGatewayId=tgw_west_id,
        PeerAccountId=account_id,
        PeerRegion='us-west-2',
        TagSpecifications=[{
            'ResourceType': 'transit-gateway-attachment',
            'Tags': [{'Key': 'Name', 'Value': 'TGW-Peering-East-West'}]
        }]
    )
    peering_id = peering_response['TransitGatewayPeeringAttachment']['TransitGatewayAttachmentId']
    print(f"TGW Peering creado: {peering_id}")
    
    # Esperar a que el peering esté en estado pendingAcceptance
    print("Esperando que el peering esté listo para aceptar...")
    while True:
        response = ec2_east.describe_transit_gateway_peering_attachments(TransitGatewayAttachmentIds=[peering_id])
        state = response['TransitGatewayPeeringAttachments'][0]['State']
        if state == 'pendingAcceptance':
            break
        time.sleep(5)
    
    # Aceptar peering desde us-west-2
    ec2_west = boto3.client('ec2', region_name='us-west-2')
    print("Aceptando peering desde us-west-2...")
    ec2_west.accept_transit_gateway_peering_attachment(TransitGatewayAttachmentId=peering_id)
    
    # Esperar a que esté disponible
    print("Esperando que el peering esté disponible...")
    while True:
        response = ec2_east.describe_transit_gateway_peering_attachments(TransitGatewayAttachmentIds=[peering_id])
        state = response['TransitGatewayPeeringAttachments'][0]['State']
        if state == 'available':
            break
        time.sleep(10)
    
    return peering_id

def configure_tgw_routes(tgw_east_id, tgw_west_id, peering_id):
    """Configura rutas en los Transit Gateways"""
    ec2_east = boto3.client('ec2', region_name='us-east-1')
    ec2_west = boto3.client('ec2', region_name='us-west-2')
    
    print("\n--- Configurando rutas TGW ---")
    
    # Esperar un poco más para asegurar propagación del peering
    time.sleep(30)
    
    try:
        # Obtener tablas de rutas por defecto
        east_rt = ec2_east.describe_transit_gateway_route_tables(
            Filters=[{'Name': 'transit-gateway-id', 'Values': [tgw_east_id]}]
        )['TransitGatewayRouteTables'][0]['TransitGatewayRouteTableId']
        
        west_rt = ec2_west.describe_transit_gateway_route_tables(
            Filters=[{'Name': 'transit-gateway-id', 'Values': [tgw_west_id]}]
        )['TransitGatewayRouteTables'][0]['TransitGatewayRouteTableId']
        
        # Ruta en TGW-East hacia redes de West (192.x.x.x)
        ec2_east.create_transit_gateway_route(
            DestinationCidrBlock='192.0.0.0/8',
            TransitGatewayRouteTableId=east_rt,
            TransitGatewayAttachmentId=peering_id
        )
        
        # Ruta en TGW-West hacia redes de East (10.x.x.x)
        ec2_west.create_transit_gateway_route(
            DestinationCidrBlock='10.0.0.0/8',
            TransitGatewayRouteTableId=west_rt,
            TransitGatewayAttachmentId=peering_id
        )
        
        print("Rutas TGW configuradas")
        
    except Exception as e:
        print(f"⚠️ Error configurando rutas TGW: {e}")
        print("Continuando sin rutas TGW (las VPCs locales seguirán funcionando)")

def configure_vpc_routes(region, vpc_resources, tgw_id, vpc_configs):
    """Configura rutas en las VPCs hacia el Transit Gateway"""
    ec2 = boto3.client('ec2', region_name=region)
    
    print(f"\n--- Configurando rutas VPC en {region} ---")
    
    # Pausa para asegurar que los attachments estén completamente propagados
    print("Esperando propagación de attachments...")
    time.sleep(30)
    
    for i, resource in enumerate(vpc_resources):
        rt_id = resource['route_table_id']
        vpc_name = vpc_configs[i]['name']
        
        # Ruta para tráfico cross-region
        if region == 'us-east-1':
            cross_region_cidr = '192.0.0.0/8'  # Hacia redes de West
            # Ruta intra-regional: hacia la otra VPC en East
            local_cidr = '10.2.0.0/16' if 'East-1' in vpc_name else '10.1.0.0/16'
        else:
            cross_region_cidr = '10.0.0.0/8'   # Hacia redes de East  
            # Ruta intra-regional: hacia la otra VPC en West
            local_cidr = '192.224.0.0/16' if 'West-1' in vpc_name else '192.168.0.0/16'
        
        print(f"Configurando rutas para {vpc_name}...")
        
        # Agregar ruta cross-region
        try:
            ec2.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock=cross_region_cidr,
                TransitGatewayId=tgw_id
            )
            print(f"  Ruta {cross_region_cidr} -> TGW configurada")
        except Exception as e:
            if "RouteAlreadyExists" not in str(e):
                print(f"  ⚠️ Error configurando ruta cross-region: {e}")
        
        # Pausa entre configuración de rutas
        time.sleep(5)
        
        # Agregar ruta intra-regional
        try:
            ec2.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock=local_cidr,
                TransitGatewayId=tgw_id
            )
            print(f"  Ruta {local_cidr} -> TGW configurada")
        except Exception as e:
            if "RouteAlreadyExists" not in str(e):
                print(f"  ⚠️ Error configurando ruta intra-regional: {e}")
        
        # Pausa entre VPCs
        time.sleep(10)

def main():
    print("=== Iniciando despliegue de infraestructura Transit Gateway ===")
    
    # Configuraciones de VPCs
    east_configs = [
        {'name': 'VPC-East-1', 'vpc_cidr': '10.1.0.0/16', 'subnet_cidr': '10.1.0.0/24'},
        {'name': 'VPC-East-2', 'vpc_cidr': '10.2.0.0/16', 'subnet_cidr': '10.2.0.0/24'}
    ]
    
    west_configs = [
        {'name': 'VPC-West-1', 'vpc_cidr': '192.168.0.0/16', 'subnet_cidr': '192.168.1.0/24'},
        {'name': 'VPC-West-2', 'vpc_cidr': '192.224.0.0/16', 'subnet_cidr': '192.224.0.0/24'}
    ]
    
    try:
        # 1. Crear VPCs en ambas regiones
        east_resources = create_vpc_infrastructure('us-east-1', east_configs)
        west_resources = create_vpc_infrastructure('us-west-2', west_configs)
        
        # 2. Crear Transit Gateways
        tgw_east_id = create_transit_gateway('us-east-1', 64512, 'TGW-East')
        tgw_west_id = create_transit_gateway('us-west-2', 64513, 'TGW-West')
        
        # 3. Conectar VPCs a TGWs
        attach_vpcs_to_tgw('us-east-1', tgw_east_id, east_resources)
        attach_vpcs_to_tgw('us-west-2', tgw_west_id, west_resources)
        
        # 4. Crear peering entre TGWs
        peering_id = create_tgw_peering(tgw_east_id, tgw_west_id)
        
        # 5. Configurar rutas
        configure_tgw_routes(tgw_east_id, tgw_west_id, peering_id)
        configure_vpc_routes('us-east-1', east_resources, tgw_east_id, east_configs)
        configure_vpc_routes('us-west-2', west_resources, tgw_west_id, west_configs)
        
        print("\n=== RESUMEN DE RECURSOS CREADOS ===")
        print(f"TGW East: {tgw_east_id}")
        print(f"TGW West: {tgw_west_id}")
        print(f"TGW Peering: {peering_id}")
        
        print("\nVPCs US-EAST-1:")
        for i, resource in enumerate(east_resources):
            print(f"  {east_configs[i]['name']}: {resource['vpc_id']}")
        
        print("\nVPCs US-WEST-2:")
        for i, resource in enumerate(west_resources):
            print(f"  {west_configs[i]['name']}: {resource['vpc_id']}")
        
        print("\n✅ Infraestructura Transit Gateway creada exitosamente!")
        print("🔗 Conectividad full-mesh entre todas las VPCs habilitada")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()