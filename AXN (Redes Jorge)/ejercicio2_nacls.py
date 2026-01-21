import boto3
import time

# --- CONFIGURACIÓN ---
REGION = 'us-east-1'
VPC_CIDR = '10.0.0.0/16'
SUBNET_PUB_CIDR = '10.0.1.0/24'
SUBNET_PRIV_CIDR = '10.0.2.0/24'

ec2 = boto3.resource('ec2', region_name=REGION)
client = boto3.client('ec2', region_name=REGION)

def log(msg):
    print(f"[NACLs] {msg}")

def main():
    try:
        log("--- INICIANDO ESCENARIO NACLs (EJERCICIO 2) ---")

        # 1. Crear VPC Base
        vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)
        vpc.create_tags(Tags=[{"Key": "Name", "Value": "VPC-Ejercicio2-NACLs"}])
        vpc.wait_until_available()
        log(f"VPC creada: {vpc.id}")

        # 2. Subredes
        sn_pub = vpc.create_subnet(CidrBlock=SUBNET_PUB_CIDR, AvailabilityZone=f'{REGION}a')
        sn_pub.create_tags(Tags=[{"Key": "Name", "Value": "Subnet-Publica-NACL"}])
        
        sn_priv = vpc.create_subnet(CidrBlock=SUBNET_PRIV_CIDR, AvailabilityZone=f'{REGION}a')
        sn_priv.create_tags(Tags=[{"Key": "Name", "Value": "Subnet-Privada-NACL"}])
        log("Subredes creadas.")

        # 3. Internet Gateway (necesario para definir 'Internet' en la pública)
        igw = ec2.create_internet_gateway()
        vpc.attach_internet_gateway(InternetGatewayId=igw.id)
        
        # 4. CREACIÓN DE NACL PÚBLICO (La parte clave)
        log("Configurando NACL Público...")
        nacl_pub = vpc.create_network_acl()
        nacl_pub.create_tags(Tags=[{"Key": "Name", "Value": "NACL-Publico-Estricto"}])

        # REGLAS DE ENTRADA (Inbound)
        # 100: Permitir HTTP (80) desde Internet
        nacl_pub.create_entry(RuleNumber=100, Protocol='6', PortRange={'From': 80, 'To': 80}, Egress=False, RuleAction='allow', CidrBlock='0.0.0.0/0')
        # 110: Permitir HTTPS (443) desde Internet
        nacl_pub.create_entry(RuleNumber=110, Protocol='6', PortRange={'From': 443, 'To': 443}, Egress=False, RuleAction='allow', CidrBlock='0.0.0.0/0')
        # 120: Permitir Tráfico de retorno desde la Privada (Para que puedan hablar)
        nacl_pub.create_entry(RuleNumber=120, Protocol='-1', Egress=False, RuleAction='allow', CidrBlock=SUBNET_PRIV_CIDR)
        # IMPORTANTE: Permitir puertos efímeros de retorno desde internet (si el servidor inicia la conexión)
        nacl_pub.create_entry(RuleNumber=140, Protocol='6', PortRange={'From': 1024, 'To': 65535}, Egress=False, RuleAction='allow', CidrBlock='0.0.0.0/0')

        # REGLAS DE SALIDA (Outbound)
        # 100: Permitir responder a Internet (Puertos efímeros)
        nacl_pub.create_entry(RuleNumber=100, Protocol='6', PortRange={'From': 1024, 'To': 65535}, Egress=True, RuleAction='allow', CidrBlock='0.0.0.0/0')
        # 110: Permitir hablar hacia la Privada
        nacl_pub.create_entry(RuleNumber=110, Protocol='-1', Egress=True, RuleAction='allow', CidrBlock=SUBNET_PRIV_CIDR)
        
        # ASOCIAR NACL a Subred Pública
        # Hay que reemplazar la asociación por defecto
        assoc_pub = client.describe_network_acls(Filters=[{'Name': 'association.subnet-id', 'Values': [sn_pub.id]}])['NetworkAcls'][0]['Associations'][0]['NetworkAclAssociationId']
        client.replace_network_acl_association(AssociationId=assoc_pub, NetworkAclId=nacl_pub.id)
        log("NACL Público configurado y asociado.")

        # 5. CREACIÓN DE NACL PRIVADO
        log("Configurando NACL Privado...")
        nacl_priv = vpc.create_network_acl()
        nacl_priv.create_tags(Tags=[{"Key": "Name", "Value": "NACL-Privado-Aislado"}])

        # REGLAS ENTRADA: Solo desde la Pública
        nacl_priv.create_entry(RuleNumber=100, Protocol='-1', Egress=False, RuleAction='allow', CidrBlock=SUBNET_PUB_CIDR)
        
        # REGLAS SALIDA: Solo hacia la Pública
        nacl_priv.create_entry(RuleNumber=100, Protocol='-1', Egress=True, RuleAction='allow', CidrBlock=SUBNET_PUB_CIDR)

        # ASOCIAR NACL a Subred Privada
        assoc_priv = client.describe_network_acls(Filters=[{'Name': 'association.subnet-id', 'Values': [sn_priv.id]}])['NetworkAcls'][0]['Associations'][0]['NetworkAclAssociationId']
        client.replace_network_acl_association(AssociationId=assoc_priv, NetworkAclId=nacl_priv.id)
        log("NACL Privado configurado y asociado.")

        print("\n" + "="*50)
        print("ESCENARIO COMPLETADO")
        print("="*50)
        print("Ve a la consola de AWS -> VPC -> Network ACLs")
        print(f"Verifica 'NACL-Publico-Estricto' y 'NACL-Privado-Aislado'")
        print("="*50)

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == '__main__':
    main()