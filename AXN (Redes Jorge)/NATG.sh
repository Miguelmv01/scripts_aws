#!/bin/bash

# ==========================================
# CONFIGURACIÓN INICIAL (VPC, SUBREDES, EC2)
# ==========================================
REGION="us-east-1"
AMI_ID="ami-0ecb62995f68bb549"
KEY_NAME="vockey"
IAM_PROFILE="LabInstanceProfile"

echo "--- Iniciando despliegue de infraestructura para miguel ---"

# 1. CREAR VPC
# Creamos la VPC y capturamos su ID
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --region $REGION \
    --query 'Vpc.VpcId' --output text)

# Creamos la VPC
aws ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=miguel-vpc --region $REGION
echo "VPC creada: $VPC_ID"

# 2. Creamos el IGW
IGW_ID=$(aws ec2 create-internet-gateway \
    --region $REGION \
    --query 'InternetGateway.InternetGatewayId' --output text)

aws ec2 create-tags --resources $IGW_ID --tags Key=Name,Value=miguel-igw --region $REGION
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID --region $REGION
echo "Internet Gateway creado y adjuntado: $IGW_ID"

# 3. Creamos ambas Subredes
# Subred Pública (10.0.1.0/24)
SUBNET_PUB_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone ${REGION}a \
    --region $REGION \
    --query 'Subnet.SubnetId' --output text)

aws ec2 create-tags --resources $SUBNET_PUB_ID --tags Key=Name,Value=miguel-subnet-publica --region $REGION
# Habilitar asignación automática de IP pública
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_PUB_ID --map-public-ip-on-launch --region $REGION
echo "Subred Pública creada: $SUBNET_PUB_ID"

# Subred Privada (10.0.2.0/24)
SUBNET_PRIV_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone ${REGION}a \
    --region $REGION \
    --query 'Subnet.SubnetId' --output text)

aws ec2 create-tags --resources $SUBNET_PRIV_ID --tags Key=Name,Value=miguel-subnet-privada --region $REGION
echo "Subred Privada creada: $SUBNET_PRIV_ID"

# 4. GRUPO DE SEGURIDAD
SG_ID=$(aws ec2 create-security-group \
    --group-name "miguel-security-group" \
    --description "Permitir SSH e ICMP para Miguel" \
    --vpc-id $VPC_ID \
    --region $REGION \
    --query 'GroupId' --output text)

aws ec2 create-tags --resources $SG_ID --tags Key=Name,Value=miguel-sg --region $REGION

# Regla entrada: SSH (22) desde 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr 0.0.0.0/0 --region $REGION
# Regla entrada: ICMP (Ping) desde 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol icmp --port -1 --cidr 0.0.0.0/0 --region $REGION
echo "Security Group creado: $SG_ID"

# 5. TABLAS DE ENRUTAMIENTO

# --- Tabla Pública ---
RT_PUB_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID --region $REGION --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-tags --resources $RT_PUB_ID --tags Key=Name,Value=miguel-rt-publica --region $REGION
# Ruta al IGW
aws ec2 create-route --route-table-id $RT_PUB_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID --region $REGION > /dev/null
# Asociar a Subred Pública
aws ec2 associate-route-table --subnet-id $SUBNET_PUB_ID --route-table-id $RT_PUB_ID --region $REGION
echo "Tabla de rutas pública configurada."

# --- Tabla Privada ---
RT_PRIV_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID --region $REGION --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-tags --resources $RT_PRIV_ID --tags Key=Name,Value=miguel-rt-privada --region $REGION
# Asociar a Subred Privada (SIN RUTA DE SALIDA AUN)
aws ec2 associate-route-table --subnet-id $SUBNET_PRIV_ID --route-table-id $RT_PRIV_ID --region $REGION
echo "Tabla de rutas privada configurada (sin salida a internet)."

# 6. LANZAR INSTANCIAS EC2

echo "Lanzando instancias (esto puede tardar unos segundos)..."

# Instancia Pública
INSTANCE_PUB_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --count 1 \
    --instance-type t3.micro \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --subnet-id $SUBNET_PUB_ID \
    --iam-instance-profile Name=$IAM_PROFILE \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=miguel-ec2-publica}]" \
    --region $REGION \
    --query 'Instances[0].InstanceId' --output text)

# Instancia Privada
INSTANCE_PRIV_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --count 1 \
    --instance-type t3.micro \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --subnet-id $SUBNET_PRIV_ID \
    --iam-instance-profile Name=$IAM_PROFILE \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=miguel-ec2-privada}]" \
    --region $REGION \
    --query 'Instances[0].InstanceId' --output text)

# Esperar a que estén "Running" para obtener las IPs
aws ec2 wait instance-running --instance-ids $INSTANCE_PUB_ID $INSTANCE_PRIV_ID --region $REGION

# Obtener IPs
PUB_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_PUB_ID --region $REGION --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
PRIV_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_PRIV_ID --region $REGION --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)

echo "=========================================="
echo " DESPLIEGUE BASE COMPLETADO"
echo "=========================================="
echo "EC2 Pública ($INSTANCE_PUB_ID): $PUB_IP"
echo "EC2 Privada ($INSTANCE_PRIV_ID): $PRIV_IP"
echo ""
echo "Comandos para conectar:"
echo "1. SSH a la pública: ssh -i $KEY_NAME.pem -A ubuntu@$PUB_IP"
echo "2. Desde ahí a la privada: ssh ubuntu@$PRIV_IP"
echo "3. En la privada prueba: ping google.com (Debería FALLAR ahora)"
echo "=========================================="


# =========================================================================
#  PARTE 2: NAT GATEWAY Y ENRUTAMIENTO
# =========================================================================

echo "--- Iniciando Fase 2: Creación de NAT Gateway ---"

# 1. Recuperar IDs necesarios por Tags (para no depender de las variables de arriba si reinicias la sesión)
SUBNET_PUB_ID=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=miguel-subnet-publica" --region $REGION --query "Subnets[0].SubnetId" --output text)
RT_PRIV_ID=$(aws ec2 describe-route-tables --filters "Name=tag:Name,Values=miguel-rt-privada" --region $REGION --query "RouteTables[0].RouteTableId" --output text)

# 2. Crear Elastic IP
EIP_ALLOC_ID=$(aws ec2 allocate-address --domain vpc --region $REGION --query 'AllocationId' --output text)
aws ec2 create-tags --resources $EIP_ALLOC_ID --tags Key=Name,Value=miguel-nat-eip --region $REGION
echo "Elastic IP creada: $EIP_ALLOC_ID"

# 3. Crear NAT Gateway
NAT_GW_ID=$(aws ec2 create-nat-gateway \
    --subnet-id $SUBNET_PUB_ID \
    --allocation-id $EIP_ALLOC_ID \
    --region $REGION \
    --query 'NatGateway.NatGatewayId' --output text)

aws ec2 create-tags --resources $NAT_GW_ID --tags Key=Name,Value=miguel-nat-gw --region $REGION
echo "Creando NAT Gateway ($NAT_GW_ID)... Esperando a que esté disponible (esto tarda 1-2 mins)..."

# 4. Esperar a que la NAT esté disponible
aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT_GW_ID --region $REGION
echo "NAT Gateway disponible."

# 5. Modificar la Tabla de Rutas Privada
aws ec2 create-route \
    --route-table-id $RT_PRIV_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --nat-gateway-id $NAT_GW_ID \
    --region $REGION > /dev/null

echo "Ruta añadida: 0.0.0.0/0 -> $NAT_GW_ID en la tabla privada."

# echo "=========================================="
# echo " FASE 2 COMPLETADA: Prueba el ping ahora."
# echo "=========================================="