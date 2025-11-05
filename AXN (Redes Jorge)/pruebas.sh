#creo el grupo de seguridad permitiendo ssh
SG_ID=$(aws ec2 create-security-group --vpc-id vpc-0ebb4bf62de0c540d \
 --group-name gsmio \
 --description "Mi grupo de seguridad para abrir el puerto 22" \
 --query GroupId --output text)

 echo "Y ahora el grupo de seguridad"
 echo $SG_ID

aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp \
    --port 22 \
    --cidr 0.0.0.0/0