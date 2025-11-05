#!/bin/bash
# =====================================================
# Script: copia_instancia.sh
# Descripción: Copia una instancia EC2 de una región a otra
#              utilizando exclusivamente los comandos del ejercicio.
# Uso: ./copia_instancia.sh <region_origen> <id_instancia_origen> <region_destino>
# Ejemplo: ./copia_instancia.sh us-east-1 i-06bbec1625dbe5a14 us-west-2
# =====================================================

# -------- Comprobación de parámetros --------
if [ "$#" -ne 3 ]; then
  echo "Uso: $0 <region_origen> <id_instancia_origen> <region_destino>"
  exit 1
fi

REGION_ORIGEN=$1
INSTANCE_ID=$2
REGION_DESTINO=$3

echo "======================"
echo "🟢 INICIO DEL SCRIPT"
echo "Región origen: $REGION_ORIGEN"
echo "Instancia origen: $INSTANCE_ID"
echo "Región destino: $REGION_DESTINO"
echo "======================"

# -------- 1️⃣ Comprobar que la instancia existe --------
echo "🔍 Comprobando la existencia de la instancia origen..."
aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION_ORIGEN" \
  --output text &>/dev/null

if [ $? -ne 0 ]; then
  echo "❌ ERROR: La instancia $INSTANCE_ID no existe en $REGION_ORIGEN."
  exit 1
fi
echo "✅ Instancia encontrada en $REGION_ORIGEN."

# -------- 2️⃣ Crear la imagen (AMI) --------
AMI_NAME="AMI-$(date +%Y%m%d%H%M%S)"
echo "📸 Creando imagen '$AMI_NAME' desde la instancia origen..."
IMAGE_ID=$(aws ec2 create-image \
  --instance-id "$INSTANCE_ID" \
  --name "$AMI_NAME" \
  --no-reboot \
  --region "$REGION_ORIGEN" \
  --query 'ImageId' \
  --output text)

if [ -z "$IMAGE_ID" ]; then
  echo "❌ ERROR: No se pudo crear la AMI."
  exit 1
fi
echo "✅ Imagen creada con ID: $IMAGE_ID"

# -------- 3️⃣ Esperar a que la imagen esté disponible --------
echo "🕒 Esperando a que la AMI ($IMAGE_ID) esté disponible..."
aws ec2 wait image-available \
  --image-ids "$IMAGE_ID" \
  --region "$REGION_ORIGEN"
echo "✅ Imagen $IMAGE_ID disponible en $REGION_ORIGEN."

# -------- 4️⃣ Copiar la imagen a la región destino --------
echo "📦 Copiando la imagen a la región $REGION_DESTINO..."
COPIED_IMAGE_ID=$(aws ec2 copy-image \
  --source-image-id "$IMAGE_ID" \
  --source-region "$REGION_ORIGEN" \
  --region "$REGION_DESTINO" \
  --name "${AMI_NAME}-copia" \
  --query 'ImageId' \
  --output text)

if [ -z "$COPIED_IMAGE_ID" ]; then
  echo "❌ ERROR: No se pudo copiar la AMI a $REGION_DESTINO."
  exit 1
fi
echo "✅ Imagen copiada con ID: $COPIED_IMAGE_ID"

# -------- 5️⃣ Esperar a que la copia esté disponible --------
echo "🕒 Esperando a que la imagen copiada ($COPIED_IMAGE_ID) esté disponible..."
aws ec2 wait image-available \
  --image-ids "$COPIED_IMAGE_ID" \
  --region "$REGION_DESTINO"
echo "✅ Imagen copiada disponible en $REGION_DESTINO."

# -------- 6️⃣ Crear un par de claves en la región destino --------
KEY_NAME="Key-$(date +%Y%m%d%H%M%S)"
echo "🔑 Creando par de claves '$KEY_NAME' en $REGION_DESTINO..."
aws ec2 create-key-pair \
  --key-name "$KEY_NAME" \
  --region "$REGION_DESTINO" \
  --query "KeyMaterial" \
  --output text > "${KEY_NAME}.pem"

if [ ! -s "${KEY_NAME}.pem" ]; then
  echo "❌ ERROR: No se pudo crear el par de claves."
  exit 1
fi
chmod 400 "${KEY_NAME}.pem"
echo "✅ Par de claves creado y guardado como ${KEY_NAME}.pem"

# -------- 7️⃣ Lanzar una nueva instancia en la región destino --------
echo "🚀 Lanzando una nueva instancia en $REGION_DESTINO con la AMI copiada..."
INSTANCE_DEST_ID=$(aws ec2 run-instances \
  --image-id "$COPIED_IMAGE_ID" \
  --instance-type t3.micro \
  --key-name "$KEY_NAME" \
  --region "$REGION_DESTINO" \
  --query "Instances[0].InstanceId" \
  --output text)

if [ -z "$INSTANCE_DEST_ID" ]; then
  echo "❌ ERROR: No se pudo lanzar la nueva instancia."
  exit 1
fi
echo "✅ Instancia lanzada con ID: $INSTANCE_DEST_ID"

# -------- 8️⃣ Esperar a que la instancia esté corriendo --------
echo "🕒 Esperando a que la instancia ($INSTANCE_DEST_ID) esté en ejecución..."
aws ec2 wait instance-running \
  --instance-ids "$INSTANCE_DEST_ID" \
  --region "$REGION_DESTINO"
echo "✅ Instancia $INSTANCE_DEST_ID está en ejecución en $REGION_DESTINO."

# -------- 9️⃣ Eliminar las AMIs creadas --------
echo "🧹 Eliminando AMIs temporales..."
aws ec2 deregister-image --image-id "$IMAGE_ID" --region "$REGION_ORIGEN"
aws ec2 deregister-image --image-id "$COPIED_IMAGE_ID" --region "$REGION_DESTINO"
echo "✅ AMIs eliminadas."

echo "🎉 PROCESO COMPLETADO CON ÉXITO"
echo "📍 Nueva instancia: $INSTANCE_DEST_ID en $REGION_DESTINO"