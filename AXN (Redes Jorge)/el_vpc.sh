REGION="us-east-1"           
PAUSE_AFTER_TERMINATION=20
# Obtén los IDs de las VPCs que tienen la etiqueta entorno=prueba
VPC_IDS=$(aws ec2 describe-vpcs \
    --filters "Name=tag:entorno,Values=prueba" \
    --query "Vpcs[*].VpcId" \
    --output text)

# Recorre cada ID de VPC y elimínala
for VPC_ID in $VPC_IDS; do
    echo "Eliminando VPC $VPC_ID..."
    
    # Eliminar recursos asociados (puentes de internet, subredes, etc.) antes de eliminar la VPC
    # Ejemplo: elimina subredes
    SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[*].SubnetId" --output text)
    
    for SUBNET_ID in $SUBNET_IDS; do
        echo "---"
    echo "Bucle Exterior: Procesando Subred **$SUBNET_ID**..."
    
    # 2. Bucle Interior: Buscar y Terminar Instancias EC2 asociadas a esta Subred
    echo "  Buscando instancias EC2 activas en la subred $SUBNET_ID..."
    
    # Obtener IDs de instancias activas (no terminadas) en la subred actual
    INSTANCE_IDS=$(aws ec2 describe-instances \
        --region $REGION \
        --filters "Name=subnet-id,Values=$SUBNET_ID" "Name=instance-state-name,Values=pending,running,shutting-down,stopping,stopped" \
        --query "Reservations[].Instances[].InstanceId" \
        --output text)

    if [ ! -z "$INSTANCE_IDS" ]; then
        echo "  Instancias encontradas: $INSTANCE_IDS"
        
        # Terminar las instancias
        aws ec2 terminate-instances \
            --instance-ids $INSTANCE_IDS \
            --region $REGION
            
        echo "  Instancias enviadas a terminación. Esperando **$PAUSE_AFTER_TERMINATION** segundos..."
        sleep $PAUSE_AFTER_TERMINATION
    else
        echo "No se encontraron instancias EC2 activas en la subred."
    fi

    # 3. Intentar eliminar la Subred después de la terminación (bucle exterior)
    echo "  Intentando eliminar la Subred $SUBNET_ID..."
    
    # Intentar la eliminación y capturar la salida de error
    DELETE_RESULT=$(aws ec2 delete-subnet \
        --subnet-id "$SUBNET_ID" \
        --region "$REGION" 2>&1)
    
    if [ $? -eq 0 ]; then
        echo "Subred **$SUBNET_ID** eliminada con éxito."
    else
        echo "ERROR al eliminar la subred $SUBNET_ID. Puede que la instancia no haya terminado completamente."
        # Muestra el error de la AWS CLI para diagnóstico
        echo "$DELETE_RESULT" | grep -A 2 "Error"
    fi
done
    
    # (Opcional) Elimina más recursos aquí como Internet Gateways, Route Tables, etc., si existen
    
    # Elimina la VPC
    aws ec2 delete-vpc --vpc-id $VPC_ID
    echo "VPC $VPC_ID eliminada."
done