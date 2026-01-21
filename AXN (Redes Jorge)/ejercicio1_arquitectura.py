import boto3
import time
import sys

# --- CONFIGURACIÓN ---
REGION = 'us-east-1' 
VPC_CIDR = '15.0.0.0/20'
SUBNET_PUB_CIDR = '15.0.1.0/24'
SUBNET_PRIV_BACK_CIDR = '15.0.2.0/24'
SUBNET_PRIV_DB_CIDR = '15.0.3.0/24'
AMI_ID = 'ami-04b70fa74e45c3917' # Ubuntu 24.04 us-east-1
KEY_NAME = 'vockey' 

# Recursos Boto3
ec2 = boto3.resource('ec2', region_name=REGION)
client = boto3.client('ec2', region_name=REGION)

def log(mensaje):
    print(f"[PROGRESO] {mensaje}")

def main():
    try:
        log("--- INICIANDO DESPLIEGUE ARQUITECTURA 3 CAPAS (VERSIÓN FINAL) ---")

        # 1. Crear VPC
        log(f"Creando VPC con CIDR {VPC_CIDR}...")
        vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)
        vpc.create_tags(Tags=[{"Key": "Name", "Value": "VPC-Examen-3Capas"}])
        vpc.wait_until_available()
        
        # Habilitar DNS (Importante para que apt-get resuelva dominios)
        client.modify_vpc_attribute(VpcId=vpc.id, EnableDnsSupport={'Value': True})
        client.modify_vpc_attribute(VpcId=vpc.id, EnableDnsHostnames={'Value': True})
        log(f"VPC creada: {vpc.id}")

        # 2. Crear Internet Gateway
        igw = ec2.create_internet_gateway()
        vpc.attach_internet_gateway(InternetGatewayId=igw.id)
        igw.create_tags(Tags=[{"Key": "Name", "Value": "IGW-Examen"}])
        log("IGW creado.")

        # 3. Crear Subredes
        log("Creando Subredes...")
        subnet_pub = vpc.create_subnet(CidrBlock=SUBNET_PUB_CIDR, AvailabilityZone=f'{REGION}a')
        subnet_pub.create_tags(Tags=[{"Key": "Name", "Value": "Subnet-Publica-Frontend"}])
        
        subnet_priv_back = vpc.create_subnet(CidrBlock=SUBNET_PRIV_BACK_CIDR, AvailabilityZone=f'{REGION}a')
        subnet_priv_back.create_tags(Tags=[{"Key": "Name", "Value": "Subnet-Privada-Backend"}])

        subnet_priv_db = vpc.create_subnet(CidrBlock=SUBNET_PRIV_DB_CIDR, AvailabilityZone=f'{REGION}b')
        subnet_priv_db.create_tags(Tags=[{"Key": "Name", "Value": "Subnet-Privada-DB"}])

        # 4. NAT Gateway
        log("Asignando Elastic IP y creando NAT Gateway...")
        eip = client.allocate_address(Domain='vpc')
        eip_alloc_id = eip['AllocationId']

        nat_gw = client.create_nat_gateway(
            SubnetId=subnet_pub.id, 
            AllocationId=eip_alloc_id,
            TagSpecifications=[{'ResourceType': 'natgateway', 'Tags': [{'Key': 'Name', 'Value': 'NAT-GW-Examen'}]}]
        )
        nat_gw_id = nat_gw['NatGateway']['NatGatewayId']

        log("Esperando NAT Gateway (puede tardar 3-5 minutos, no cierres)...")
        waiter_nat = client.get_waiter('nat_gateway_available')
        waiter_nat.wait(NatGatewayIds=[nat_gw_id])
        log("NAT Gateway ACTIVO.")

        # 5. Tablas de Rutas
        log("Configurando Rutas...")
        # 5.1 Pública (hacia IGW)
        rt_pub = vpc.create_route_table()
        rt_pub.create_tags(Tags=[{"Key": "Name", "Value": "RT-Publica"}])
        rt_pub.create_route(DestinationCidrBlock='0.0.0.0/0', GatewayId=igw.id)
        rt_pub.associate_with_subnet(SubnetId=subnet_pub.id)

        # 5.2 Privada (hacia NAT GW)
        rt_priv = vpc.create_route_table()
        rt_priv.create_tags(Tags=[{"Key": "Name", "Value": "RT-Privada"}])
        rt_priv.create_route(DestinationCidrBlock='0.0.0.0/0', NatGatewayId=nat_gw_id)
        rt_priv.associate_with_subnet(SubnetId=subnet_priv_back.id)
        rt_priv.associate_with_subnet(SubnetId=subnet_priv_db.id)

        # 6. Security Groups
        log("Creando Security Groups...")
        
        # SG Frontend
        sg_front = vpc.create_security_group(GroupName='SG-Frontend', Description='Acceso Web y SSH')
        sg_front.create_tags(Tags=[{"Key": "Name", "Value": "SG-Frontend"}])
        sg_front.authorize_ingress(
            IpPermissions=[
                {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ]
        )
        
        # SG Backend
        sg_back = vpc.create_security_group(GroupName='SG-Backend', Description='Acceso interno')
        sg_back.create_tags(Tags=[{"Key": "Name", "Value": "SG-Backend"}])
        
        # Regla: Permitir todo el tráfico que venga del SG Frontend
        sg_back.authorize_ingress(
            IpPermissions=[
                {
                    'IpProtocol': '-1',
                    'UserIdGroupPairs': [{'GroupId': sg_front.id}]
                }
            ]
        )

        # 7. Instancias (CORREGIDO: Usamos ec2.create_instances en vez de vpc.create_instances)
        log("Lanzando Instancias...")
        
        # Instancia Pública (Bastion)
        instance_pub = ec2.create_instances(
            ImageId=AMI_ID, InstanceType='t2.micro', KeyName=KEY_NAME, MinCount=1, MaxCount=1,
            NetworkInterfaces=[{
                'SubnetId': subnet_pub.id, 
                'DeviceIndex': 0, 
                'AssociatePublicIpAddress': True, 
                'Groups': [sg_front.id]
            }],
            TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'SRV-Frontend-Bastion'}]}]
        )[0]

        # Instancia Privada (Backend)
        instance_priv = ec2.create_instances(
            ImageId=AMI_ID, InstanceType='t2.micro', KeyName=KEY_NAME, MinCount=1, MaxCount=1,
            NetworkInterfaces=[{
                'SubnetId': subnet_priv_back.id, 
                'DeviceIndex': 0, 
                'AssociatePublicIpAddress': False, 
                'Groups': [sg_back.id]
            }],
            TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'SRV-Backend-Private'}]}]
        )[0]

        log("Esperando estado Running...")
        instance_pub.wait_until_running()
        instance_priv.wait_until_running()

        instance_pub.reload()
        instance_priv.reload()

        print("\n" + "="*50)
        print("DESPLIEGUE FINALIZADO CON ÉXITO")
        print("="*50)
        print(f"Bastion Public IP: {instance_pub.public_ip_address}")
        print(f"Backend Private IP: {instance_priv.private_ip_address}")
        print("="*50)
        print("PASOS PARA OBTENER CAPTURA DE APT-GET UPDATE:")
        print(f"1. ssh -i {KEY_NAME}.pem ubuntu@{instance_pub.public_ip_address}")
        print(f"2. nano key.pem (pega tu clave) -> chmod 400 key.pem")
        print(f"3. ssh -i key.pem ubuntu@{instance_priv.private_ip_address}")
        print("4. sudo apt-get update")
        print("="*50)

    except Exception as e:
        print(f"[ERROR CRÍTICO] {e}")

if __name__ == '__main__':
    main()