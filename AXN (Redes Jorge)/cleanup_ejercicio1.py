import boto3
import time

REGION = 'us-east-1'
VPC_TAG_NAME = "VPC-Examen-3Capas"

ec2 = boto3.resource('ec2', region_name=REGION)
client = boto3.client('ec2', region_name=REGION)

def log(msg):
    print(f"[LIMPIEZA] {msg}")

def cleanup():
    # 1. Buscar la VPC creada anteriormente
    vpcs = list(ec2.vpcs.filter(Filters=[{'Name': 'tag:Name', 'Values': [VPC_TAG_NAME]}]))
    
    if not vpcs:
        log("No se encontró ninguna VPC con la etiqueta especificada. Nada que borrar.")
        return

    target_vpc = vpcs[0]
    vpc_id = target_vpc.id
    log(f"Encontrada VPC: {vpc_id}. Iniciando destrucción...")

    # 2. Terminar Instancias
    log("Terminando instancias...")
    instances = target_vpc.instances.all()
    instance_ids = [i.id for i in instances]
    if instance_ids:
        for instance in instances:
            instance.terminate()
        
        log(f"Esperando a que las instancias terminen: {instance_ids}")
        waiter = client.get_waiter('instance_terminated')
        waiter.wait(InstanceIds=instance_ids)
    else:
        log("No había instancias.")

    # 3. Borrar NAT Gateways
    log("Buscando NAT Gateways...")
    nat_gws = client.describe_nat_gateways(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    
    for nat in nat_gws['NatGateways']:
        if nat['State'] not in ['deleted', 'deleting']:
            nat_id = nat['NatGatewayId']
            log(f"Borrando NAT Gateway {nat_id} (esto tarda)...")
            client.delete_nat_gateway(NatGatewayId=nat_id)
            
            # Esperar borrado
            waiter_nat = client.get_waiter('nat_gateway_deleted')
            waiter_nat.wait(NatGatewayIds=[nat_id])
            
            # Liberar Elastic IP asociada si existe
            for address in nat['NatGatewayAddresses']:
                alloc_id = address.get('AllocationId')
                if alloc_id:
                    try:
                        log(f"Liberando Elastic IP {alloc_id}")
                        client.release_address(AllocationId=alloc_id)
                    except Exception as e:
                        log(f"Error liberando IP: {e}")

    # 4. Internet Gateways
    for igw in target_vpc.internet_gateways.all():
        log(f"Desconectando y borrando IGW {igw.id}")
        target_vpc.detach_internet_gateway(InternetGatewayId=igw.id)
        igw.delete()

    # 5. Subredes
    for subnet in target_vpc.subnets.all():
        log(f"Borrando Subred {subnet.id}")
        # A veces tarda un poco en sincronizar que las interfaces de red se borraron
        time.sleep(2) 
        try:
            subnet.delete()
        except Exception as e:
            log(f"Reintentando borrado de subred por dependencia pendiente... {e}")
            time.sleep(10)
            subnet.delete()

    # 6. Route Tables (excepto la Main)
    for rt in target_vpc.route_tables.all():
        is_main = False
        for assoc in rt.associations:
            if assoc.main:
                is_main = True
                break
        if not is_main:
            log(f"Borrando Tabla de Rutas {rt.id}")
            rt.delete()

    # 7. Security Groups (excepto el default)
    for sg in target_vpc.security_groups.all():
        if sg.group_name != 'default':
            log(f"Borrando Security Group {sg.group_name} ({sg.id})")
            try:
                sg.delete()
            except Exception as e:
                log(f"No se pudo borrar SG {sg.id}: {e}")

    # 8. Borrar VPC
    log(f"Borrando VPC {vpc_id}...")
    target_vpc.delete()
    log("LIMPIEZA COMPLETADA.")

if __name__ == '__main__':
    cleanup()