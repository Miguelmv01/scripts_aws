#!/bin/bash

# Configuración Global
REGION="us-east-1"
# Usamos Amazon Linux 2. Si falla, prueba con Amazon Linux 2023: ami-0230bd60aa48260c6
AMI_ID="ami-0c614dee691cbbf37" 

echo "--- INICIANDO DESPLIEGUE (CORREGIDO) EN: $REGION ---"

# 1. OBTENER VPC Y SUBNET
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --region $REGION --query "Vpcs[0].VpcId" --output text)
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region $REGION --query "Subnets[0].SubnetId" --output text)

echo "VPC: $VPC_ID | Subnet: $SUBNET_ID"

# 2. SEGURIDAD (Security Group) - CORRECCIÓN AQUÍ
echo "--- Creando/Buscando Security Group ---"

# Intentamos crear y filtramos SOLO el GroupId
SG_ID=$(aws ec2 create-security-group \
    --group-name SG-Lab-ELB-Fixed \
    --description "SG Lab ELB Fixed" \
    --vpc-id $VPC_ID \
    --region $REGION \
    --query 'GroupId' \
    --output text 2>/dev/null)

# Si falla (porque ya existe), lo buscamos
if [ -z "$SG_ID" ] || [ "$SG_ID" == "None" ]; then
    echo "El grupo ya existía, recuperando ID..."
    SG_ID=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=SG-Lab-ELB-Fixed" \
        --region $REGION \
        --query "SecurityGroups[0].GroupId" \
        --output text)
else
    echo "Grupo creado. Añadiendo regla HTTP..."
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $REGION
fi

# Limpiamos cualquier espacio en blanco que pueda haber quedado
SG_ID=$(echo $SG_ID | xargs)
echo "USANDO SECURITY GROUP ID: '$SG_ID'"

# 3. LANZAR INSTANCIA 1: BLUE
echo "--- Lanzando bluecli ---"
INSTANCE_BLUE=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --count 1 \
    --instance-type t2.micro \
    --security-group-ids "$SG_ID" \
    --subnet-id "$SUBNET_ID" \
    --region $REGION \
    --user-data '#!/bin/bash
                 yum update -y
                 yum install -y httpd
                 systemctl start httpd
                 systemctl enable httpd
                 echo "<html><body style=\"background-color:blue; color:white; text-align:center; margin-top:50px;\"><h1>APP V1: BLUE</h1><p>Instancia: bluecli</p></body></html>" > /var/www/html/index.html' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=bluecli}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

# 4. LANZAR INSTANCIA 2: GREEN
echo "--- Lanzando greencli ---"
INSTANCE_GREEN=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --count 1 \
    --instance-type t2.micro \
    --security-group-ids "$SG_ID" \
    --subnet-id "$SUBNET_ID" \
    --region $REGION \
    --user-data '#!/bin/bash
                 yum update -y
                 yum install -y httpd
                 systemctl start httpd
                 systemctl enable httpd
                 echo "<html><body style=\"background-color:green; color:white; text-align:center; margin-top:50px;\"><h1>APP V2: GREEN</h1><p>Instancia: greencli</p></body></html>" > /var/www/html/index.html' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=greencli}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "IDs: $INSTANCE_BLUE y $INSTANCE_GREEN. Esperando a que arranquen..."
aws ec2 wait instance-running --instance-ids $INSTANCE_BLUE $INSTANCE_GREEN --region $REGION

# 5. CREAR LOAD BALANCER
echo "--- Creando ELB ---"
DNS_NAME=$(aws elb create-load-balancer \
    --load-balancer-name ElbCLI \
    --listeners "Protocol=HTTP,LoadBalancerPort=80,InstanceProtocol=HTTP,InstancePort=80" \
    --subnets "$SUBNET_ID" \
    --security-groups "$SG_ID" \
    --region $REGION \
    --query 'DNSName' \
    --output text)

# 6. HEALTH CHECK
echo "--- Configurando Health Check ---"
aws elb configure-health-check \
    --load-balancer-name ElbCLI \
    --health-check Target=HTTP:80/index.html,Interval=5,Timeout=2,UnhealthyThreshold=2,HealthyThreshold=2 \
    --region $REGION

# 7. REGISTRAR INSTANCIAS
echo "--- Registrando instancias ---"
aws elb register-instances-with-load-balancer \
    --load-balancer-name ElbCLI \
    --instances $INSTANCE_BLUE $INSTANCE_GREEN \
    --region $REGION

echo "----------------------------------------------------------------"
echo "LISTO. URL DEL BALANCEADOR:"
echo "http://$DNS_NAME"
echo "----------------------------------------------------------------"