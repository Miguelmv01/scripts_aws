#Creo la VPC y devuelvo su ID 
VPC_ID=$(aws ec2 create-vpc --cidr-block 172.16.0.0/16 \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=VPCMiguel}]' \
    --query Vpc.VpcId --output text)

#Muestro la ID de la VPC
echo "VPC Creada: $VPC_ID"

#habilitar dns en la vpc
aws ec2 modify-vpc-attribute \
    --vpc-id $VPC_ID \
    --enable-dns-hostnames "{\"Value\":true}"

#Creamos la subred para la VPC 
SUB_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 172.16.0.0/20 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=mi-subred1-miguel}]' \
    --query Subnet.SubnetId --output text)

echo "Subred Creada: $SUB_ID"

# --- INICIO BLOQUE AÑADIDO PARA SALIDA A INTERNET ---

# 1. Crear el IGW para poder salir al exterior
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=mi-igw-miguel}]' \
    --query InternetGateway.InternetGatewayId --output text)
echo "IGW Creado: $IGW_ID"

# 2. Adjuntar el IGW a la VPC
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID
echo "IGW adjuntado a la VPC."

# 3. Creamos una tabla de enrutamiento
RTB_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID \
    --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=mi-rtb-miguel}]' \
    --query RouteTable.RouteTableId --output text)
echo "Tabla de Enrutamiento Creada: $RTB_ID"

# 4. Agregamos una ruta para la salida a internet
aws ec2 create-route --route-table-id $RTB_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID
echo "Ruta 0.0.0.0/0 añadida a la tabla de enrutamiento."

# 5. Asociar la tabla de enrutamiento a la subred
aws ec2 associate-route-table --subnet-id $SUB_ID --route-table-id $RTB_ID
echo "Tabla de enrutamiento asociada a la subred $SUB_ID."

# --- FIN BLOQUE AÑADIDO ---


#creo el grupo de seguridad permitiendo ssh
SG_ID=$(aws ec2 create-security-group --vpc-id $VPC_ID \
 --group-name gsmio \
 --description "Mi grupo de seguridad para abrir el puerto 22" \
 --query GroupId \
 --output text)

 echo "Y ahora el grupo de seguridad"
 echo $SG_ID

aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --ip-permissions '[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]'

aws ec2 create-tags \
    --resources $SG_ID \
    --tags "Key=Name,Value=migruposeguridad"

#creo un ec2
EC2_ID=$(aws ec2 run-instances \
    --image-id ami-0360c520857e3138f \
    --instance-type t3.micro \
    --key-name vockey \
    --subnet-id $SUB_ID \
    --security-group-ids $SG_ID \
    --private-ip-address 172.16.0.100 \
    --associate-public-ip-address \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=miec2}]' \
    --query Instances[0].InstanceId --output text)

echo "Esperando 15 segundos a que la instancia se cree..."
sleep 15

echo "Instancia EC2 Creada: $EC2_ID"