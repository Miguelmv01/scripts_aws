import boto3
import time

# --- CONFIGURACIÓN ---
REGION = 'us-east-1'
VPC_TAG_NAME = "VPC-Ejercicio2-NACLs" # El nombre que usamos en el Ejercicio 2

ec2 = boto3.resource('ec2', region_name=REGION)
client = boto3.client('ec2', region_name=REGION)

def log(msg):
    print(f"[LIMPIEZA-EJ2] {msg}")

def cleanup_ex2():
    # 1. Buscar la VPC del Ejercicio 2
    vpcs = list(ec2.vpcs.filter(Filters=[{'Name': 'tag:Name', 'Values': [VPC_TAG_NAME]}]))
    
    if not vpcs:
        log("No se encontró la VPC del Ejercicio 2. ¿Ya está borrada?")
        return

    target_vpc = vpcs[0]
    vpc_id = target_vpc.id
    log(f"Eliminando infraestructura de: {vpc_id} ({VPC_TAG_NAME})...")

    # 2. Borrar Network ACLs (NACLs) Personalizados
    # OJO: Los NACLs tienen dependencias con subredes. Primero borramos subredes.
    
    # 3. Borrar Subredes
    for subnet in target_vpc.subnets.all():
        log(f"Borrando Subred {subnet.id}...")
        try:
            client.delete_subnet(SubnetId=subnet.id)
        except Exception as e:
            log(f"Error borrando subred (reintentando en breve): {e}")
            time.sleep(5)
            client.delete_subnet(SubnetId=subnet.id)

    # 4. Ahora sí, borrar NACLs personalizados (no se puede borrar el 'default')
    nacls = client.describe_network_acls(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    for nacl in nacls['NetworkAcls']:
        if not nacl['IsDefault']:
            log(f"Borrando NACL {nacl['NetworkAclId']}...")
            client.delete_network_acl(NetworkAclId=nacl['NetworkAclId'])

    # 5. Internet Gateway
    for igw in target_vpc.internet_gateways.all():
        log(f"Desconectando y borrando IGW {igw.id}...")
        target_vpc.detach_internet_gateway(InternetGatewayId=igw.id)
        igw.delete()

    # 6. Borrar VPC
    log(f"Borrando VPC final {vpc_id}...")
    client.delete_vpc(VpcId=vpc_id)
    log("LIMPIEZA EJERCICIO 2 COMPLETADA.")

if __name__ == '__main__':
    cleanup_ex2()