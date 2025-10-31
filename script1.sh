#Creo la VPC y devuelvo su ID 
VPC_ID=$(aws ec2 create-vpc --cidr-block 192.168.0.0/24 \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=VPCMiguel}]' \
    --query Vpc.VpcId --output text)

#Muestro la ID de la VPC
echo $VPC_ID

#habilitar dns en la vpc
aws ec2 modify-vpc-attribute \
    --vpc-id $VPC_ID \
    --enable-dns-hostnames "{\"Value\":true}"

#Creamos la subred para la VPC 
SUB_ID=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 192.168.0.0/28 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=mi-subred1-miguel}]' \
    --query Subnet.SubnetId --output text)

echo $SUB_ID

#Habilito la asignacion de ipv4 publica en la subred
#comprobar como NO se habilita y tenemos que hacerlo a posteriori
aws ec2 modify-subnet-attribute --subnet $SUB_ID --map-public-ip-on-launch