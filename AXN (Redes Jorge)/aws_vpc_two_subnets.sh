#!/bin/bash

# Definimos variables
VPC_CIDR="10.0.0.0/16"
SUBNET1_CIDR="10.0.1.0/24"
SUBNET2_CIDR="10.0.2.0/24"
TAG_KEY="entorno"
TAG_VALUE="prueba"
REGION="us-east-1"
AZ1="${REGION}a"
AZ2="${REGION}b"

# --- EC2 ---
AMI_ID="ami-0360c520857e3138f"
INSTANCE_TYPE="t3.micro"
KEY_PAIR_NAME="vockey"
STATIC_PRIVATE_IP="10.0.1.100"
# ---------------------

echo "Creando la VPC con la etiqueta ${TAG_KEY}=${TAG_VALUE}..."

# 1. Crear la VPC con la etiqueta
VPC_RESULT=$(aws ec2 create-vpc \
    --cidr-block "$VPC_CIDR" \
    --region "$REGION" \
    --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=VPC-$TAG_VALUE},{Key=$TAG_KEY,Value=$TAG_VALUE}]")

# 2. Extraer ID de la VPC
VPC_ID=$(echo "$VPC_RESULT" | jq -r '.Vpc.VpcId')

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "null" ]; then
    echo "ERROR: Falló la creación de la VPC. Saliendo."
    exit 1
fi

echo "VPC creada con ID: **$VPC_ID**"
echo "---"

# 3. Crear la Subred 1 (en la primera AZ)
echo "Creando Subred 1 (${SUBNET1_CIDR}) en $AZ1..."
SUBNET1_RESULT=$(aws ec2 create-subnet \
    --vpc-id "$VPC_ID" \
    --cidr-block "$SUBNET1_CIDR" \
    --availability-zone "$AZ1" \
    --region "$REGION" \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=Subred-1-$TAG_VALUE},{Key=$TAG_KEY,Value=$TAG_VALUE}]")
    
SUBNET1_ID=$(echo "$SUBNET1_RESULT" | jq -r '.Subnet.SubnetId')
echo "Subred 1 creada con ID: **$SUBNET1_ID**"

# 4. Crear la Subred 2 (en la segunda AZ)
echo "Creando Subred 2 (${SUBNET2_CIDR}) en $AZ2..."
SUBNET2_RESULT=$(aws ec2 create-subnet \
    --vpc-id "$VPC_ID" \
    --cidr-block "$SUBNET2_CIDR" \
    --availability-zone "$AZ2" \
    --region "$REGION" \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=Subred-2-$TAG_VALUE},{Key=$TAG_KEY,Value=$TAG_VALUE}]")

SUBNET2_ID=$(echo "$SUBNET2_RESULT" | jq -r '.Subnet.SubnetId')
echo "Subred 2 creada con ID: **$SUBNET2_ID**"

echo "---"

# ## CREACIÓN Y CONFIGURACIÓN DEL GRUPO DE SEGURIDAD
# echo "Creando Grupo de Seguridad y abriendo puerto 22..."
# SG_ID=$(aws ec2 create-security-group \
#     --vpc-id "$VPC_ID" \
#     --group-name "gsmio" \
#     --description "Mi grupo de seguridad para abrir el puerto 22" \
#     --query GroupId \
#     --output text \
#     --region "$REGION")

# echo "Grupo de seguridad creado: **$SG_ID**"

# # Abrir Puerto 22 (SSH)
# aws ec2 authorize-security-group-ingress \
#     --group-id "$SG_ID" \
#     --ip-permissions '[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]' \
#     --region "$REGION"
# echo "Puerto 22 (SSH) abierto."

# # Corrección de sintaxis en tags
# aws ec2 create-tags \
#     --resources "$SG_ID" \
#     --tags "Key=Name,Value=migruposeguridad" \
#     --region "$REGION"

echo "---"

## LANZAMIENTO DE LA INSTANCIA EC2 EN SUBRED PRIVADA
echo "Lanzando instancia EC2 en Subred 1 (Privada) con IP estática $STATIC_PRIVATE_IP..."

# Se elimina --associate-public-ip-address (inconsistente con subred privada)
# Se corrige la IP privada estática
EC2_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_PAIR_NAME" \
    --subnet-id "$SUBNET1_ID" \
    --private-ip-address "$STATIC_PRIVATE_IP" \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=miec2}]' \
    --query 'Instances[0].InstanceId' \
    --output text \
    --region "$REGION")

if [ -z "$EC2_ID" ]; then
    echo "ERROR: Falló el lanzamiento de la instancia EC2. Saliendo."
    exit 1
fi

echo "Esperando 15 segundos a que la instancia se cree..."
sleep 15

echo "Creada la Instancia de EC2: **$EC2_ID**"
echo "IP Privada: **$STATIC_PRIVATE_IP**"
echo "Recordatorio: Esta instancia está en una subred privada y no tiene acceso a internet."