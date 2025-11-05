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

#creo el grupo de seguridad permitiendo ssh
SG_ID=$(aws ec2 create-security-group --vpc-id $VPC_ID \
 --group-name gsmio \
 --description "Mi grupo de seguridad para abrir el puerto 22" \
 --output text)

 echo "Y ahora el grupo de seguridad"
 echo $SG_ID

aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    # --protocol tcp \
    # --port 22 \
    # --cidr 0.0.0.0/0 > /dev/null/
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
    --associate-public-ip-address \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=miec2}]' \
    --query Instances.InstancetId --output text)

sleep 15

echo $EC2_ID


