import boto3
import time
import sys

# --- CONFIGURACIÓN ---
REGION = "us-east-1"
PROJECT_NAME = "miguel-python"  # Prefijo para diferenciar nombres
AMI_ID = "ami-0ecb62995f68bb549" # Ubuntu en us-east-1
KEY_NAME = "vockey"
IAM_PROFILE = "LabInstanceProfile"

# CIDRs
VPC_CIDR = "10.10.0.0/16"
PUB_CIDR_1 = "10.10.1.0/24"
PUB_CIDR_2 = "10.10.2.0/24"
PRIV_CIDR_1 = "10.10.3.0/24"
PRIV_CIDR_2 = "10.10.4.0/24"
AZ_1 = f"{REGION}a"
AZ_2 = f"{REGION}b"

# Inicializar cliente EC2
ec2 = boto3.client('ec2', region_name=REGION)

def create_tag(resource_id, value):
    ec2.create_tags(Resources=[resource_id], Tags=[{'Key': 'Name', 'Value': value}])
    print(f"   -> Etiquetado: {value}")

def main():
    print(f"--- INICIANDO DESPLIEGUE BOTO3 ({PROJECT_NAME}) ---")

    # 1. CREAR VPC
    print("\n1. Creando VPC...")
    vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)
    vpc_id = vpc['Vpc']['VpcId']
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    create_tag(vpc_id, f"{PROJECT_NAME}-vpc")

    # 2. CREAR INTERNET GATEWAY
    print("\n2. Creando IGW...")
    igw = ec2.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    create_tag(igw_id, f"{PROJECT_NAME}-igw")

    # 3. CREAR SUBREDES (2 AZs)
    print("\n3. Creando Subredes...")
    
    # Public 1 (AZ A)
    sub_pub_1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock=PUB_CIDR_1, AvailabilityZone=AZ_1)
    sub_pub_1_id = sub_pub_1['Subnet']['SubnetId']
    ec2.modify_subnet_attribute(SubnetId=sub_pub_1_id, MapPublicIpOnLaunch={'Value': True})
    create_tag(sub_pub_1_id, f"{PROJECT_NAME}-sub-pub-1a")

    # Public 2 (AZ B)
    sub_pub_2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock=PUB_CIDR_2, AvailabilityZone=AZ_2)
    sub_pub_2_id = sub_pub_2['Subnet']['SubnetId']
    ec2.modify_subnet_attribute(SubnetId=sub_pub_2_id, MapPublicIpOnLaunch={'Value': True})
    create_tag(sub_pub_2_id, f"{PROJECT_NAME}-sub-pub-2b")

    # Private 1 (AZ A)
    sub_priv_1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock=PRIV_CIDR_1, AvailabilityZone=AZ_1)
    sub_priv_1_id = sub_priv_1['Subnet']['SubnetId']
    create_tag(sub_priv_1_id, f"{PROJECT_NAME}-sub-priv-1a")

    # Private 2 (AZ B)
    sub_priv_2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock=PRIV_CIDR_2, AvailabilityZone=AZ_2)
    sub_priv_2_id = sub_priv_2['Subnet']['SubnetId']
    create_tag(sub_priv_2_id, f"{PROJECT_NAME}-sub-priv-2b")

    # 4. SECURITY GROUPS
    print("\n4. Configurando Security Groups...")
    
    # SG Publico
    sg_pub = ec2.create_security_group(GroupName=f"{PROJECT_NAME}-sg-public", Description="Acceso Publico", VpcId=vpc_id)
    sg_pub_id = sg_pub['GroupId']
    create_tag(sg_pub_id, f"{PROJECT_NAME}-sg-public")
    
    # Reglas SG Publico (SSH, HTTP, ICMP)
    ec2.authorize_security_group_ingress(GroupId=sg_pub_id, IpProtocol='tcp', FromPort=22, ToPort=22, CidrIp='0.0.0.0/0')
    ec2.authorize_security_group_ingress(GroupId=sg_pub_id, IpProtocol='tcp', FromPort=80, ToPort=80, CidrIp='0.0.0.0/0')
    ec2.authorize_security_group_ingress(GroupId=sg_pub_id, IpProtocol='icmp', FromPort=-1, ToPort=-1, CidrIp='0.0.0.0/0')

    # SG Privado
    sg_priv = ec2.create_security_group(GroupName=f"{PROJECT_NAME}-sg-private", Description="Acceso Privado", VpcId=vpc_id)
    sg_priv_id = sg_priv['GroupId']
    create_tag(sg_priv_id, f"{PROJECT_NAME}-sg-private")
    
    # Regla SG Privado: Permitir TODO desde SG Publico (Encadenamiento)
    ec2.authorize_security_group_ingress(
        GroupId=sg_priv_id, 
        IpPermissions=[{
            'IpProtocol': 'tcp', 'FromPort': 0, 'ToPort': 65535,
            'UserIdGroupPairs': [{'GroupId': sg_pub_id}]
        },
        {
            'IpProtocol': 'icmp', 'FromPort': -1, 'ToPort': -1,
            'UserIdGroupPairs': [{'GroupId': sg_pub_id}]
        }]
    )

    # 5. NETWORK ACLs
    print("\n5. Configurando NACLs...")
    
    # NACL Publica
    nacl_pub = ec2.create_network_acl(VpcId=vpc_id)
    nacl_pub_id = nacl_pub['NetworkAcl']['NetworkAclId']
    create_tag(nacl_pub_id, f"{PROJECT_NAME}-nacl-public")
    
    # Reglas NACL Publica
    # Entrada (SSH, HTTP, Ephemeral)
    ec2.create_network_acl_entry(NetworkAclId=nacl_pub_id, RuleNumber=100, Protocol='6', RuleAction='allow', Egress=False, CidrBlock='0.0.0.0/0', PortRange={'From': 22, 'To': 22})
    ec2.create_network_acl_entry(NetworkAclId=nacl_pub_id, RuleNumber=110, Protocol='6', RuleAction='allow', Egress=False, CidrBlock='0.0.0.0/0', PortRange={'From': 80, 'To': 80})
    ec2.create_network_acl_entry(NetworkAclId=nacl_pub_id, RuleNumber=120, Protocol='6', RuleAction='allow', Egress=False, CidrBlock='0.0.0.0/0', PortRange={'From': 1024, 'To': 65535})
    # Salida (All)
    ec2.create_network_acl_entry(NetworkAclId=nacl_pub_id, RuleNumber=100, Protocol='-1', RuleAction='allow', Egress=True, CidrBlock='0.0.0.0/0')

    # NACL Privada
    nacl_priv = ec2.create_network_acl(VpcId=vpc_id)
    nacl_priv_id = nacl_priv['NetworkAcl']['NetworkAclId']
    create_tag(nacl_priv_id, f"{PROJECT_NAME}-nacl-private")
    
    # Reglas NACL Privada
    # Entrada (VPC CIDR allow)
    ec2.create_network_acl_entry(NetworkAclId=nacl_priv_id, RuleNumber=100, Protocol='-1', RuleAction='allow', Egress=False, CidrBlock=VPC_CIDR)
    # Salida (All)
    ec2.create_network_acl_entry(NetworkAclId=nacl_priv_id, RuleNumber=100, Protocol='-1', RuleAction='allow', Egress=True, CidrBlock='0.0.0.0/0')

    # ASOCIAR NACLS (Paso delicado en script)
    # Helper para reemplazar asociación
    def replace_nacl_assoc(subnet_id, new_nacl_id):
        # Buscar la asociación actual de la subred
        filters = [{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
        acls = ec2.describe_network_acls(Filters=filters)
        for acl in acls['NetworkAcls']:
            for assoc in acl['Associations']:
                if assoc['SubnetId'] == subnet_id:
                    assoc_id = assoc['NetworkAclAssociationId']
                    ec2.replace_network_acl_association(AssociationId=assoc_id, NetworkAclId=new_nacl_id)
    
    replace_nacl_assoc(sub_pub_1_id, nacl_pub_id)
    replace_nacl_assoc(sub_pub_2_id, nacl_pub_id)
    replace_nacl_assoc(sub_priv_1_id, nacl_priv_id)
    replace_nacl_assoc(sub_priv_2_id, nacl_priv_id)

    # 6. TABLAS DE RUTAS
    print("\n6. Tablas de Rutas...")
    
    # RT Publica
    rt_pub = ec2.create_route_table(VpcId=vpc_id)
    rt_pub_id = rt_pub['RouteTable']['RouteTableId']
    create_tag(rt_pub_id, f"{PROJECT_NAME}-rt-publica")
    ec2.create_route(RouteTableId=rt_pub_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
    ec2.associate_route_table(RouteTableId=rt_pub_id, SubnetId=sub_pub_1_id)
    ec2.associate_route_table(RouteTableId=rt_pub_id, SubnetId=sub_pub_2_id)

    # RT Privada
    rt_priv = ec2.create_route_table(VpcId=vpc_id)
    rt_priv_id = rt_priv['RouteTable']['RouteTableId']
    create_tag(rt_priv_id, f"{PROJECT_NAME}-rt-privada")
    ec2.associate_route_table(RouteTableId=rt_priv_id, SubnetId=sub_priv_1_id)
    ec2.associate_route_table(RouteTableId=rt_priv_id, SubnetId=sub_priv_2_id)

    # 7. LANZAR INSTANCIAS EC2
    print("\n7. Lanzando EC2s...")
    
    # Instancia Publica (Jump)
    inst_pub = ec2.run_instances(
        ImageId=AMI_ID, InstanceType='t3.micro', KeyName=KEY_NAME, MinCount=1, MaxCount=1,
        SubnetId=sub_pub_1_id, SecurityGroupIds=[sg_pub_id],
        IamInstanceProfile={'Name': IAM_PROFILE},
        TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': f"{PROJECT_NAME}-ec2-jump"}]}]
    )
    inst_pub_id = inst_pub['Instances'][0]['InstanceId']

    # Instancia Privada (Internal)
    inst_priv = ec2.run_instances(
        ImageId=AMI_ID, InstanceType='t3.micro', KeyName=KEY_NAME, MinCount=1, MaxCount=1,
        SubnetId=sub_priv_1_id, SecurityGroupIds=[sg_priv_id],
        IamInstanceProfile={'Name': IAM_PROFILE},
        TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': f"{PROJECT_NAME}-ec2-internal"}]}]
    )
    inst_priv_id = inst_priv['Instances'][0]['InstanceId']

    print(f"   -> Esperando a que estén Running (IDs: {inst_pub_id}, {inst_priv_id})...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[inst_pub_id, inst_priv_id])

    # 8. NAT GATEWAY
    print("\n8. Creando NAT Gateway (esto tarda un poco)...")
    eip = ec2.allocate_address(Domain='vpc')
    eip_id = eip['AllocationId']
    create_tag(eip_id, f"{PROJECT_NAME}-nat-eip")

    nat_gw = ec2.create_nat_gateway(SubnetId=sub_pub_1_id, AllocationId=eip_id)
    nat_gw_id = nat_gw['NatGateway']['NatGatewayId']
    create_tag(nat_gw_id, f"{PROJECT_NAME}-nat")
    
    print(f"   -> NAT Gateway creado ({nat_gw_id}). Esperando disponibilidad (aprox 2 min)...")
    nat_waiter = ec2.get_waiter('nat_gateway_available')
    nat_waiter.wait(NatGatewayIds=[nat_gw_id])
    
    # Añadir ruta NAT a la tabla privada
    ec2.create_route(RouteTableId=rt_priv_id, DestinationCidrBlock='0.0.0.0/0', NatGatewayId=nat_gw_id)

    print("\n==========================================")
    print(" DESPLIEGUE PYTHON FINALIZADO CON ÉXITO")
    print("==========================================")
    print(f"VPC: {vpc_id}")
    print(f"Jump Server: {inst_pub_id}")
    print(f"Internal Server: {inst_priv_id}")
    print(f"NAT Gateway: {nat_gw_id}")

if __name__ == '__main__':
    main()