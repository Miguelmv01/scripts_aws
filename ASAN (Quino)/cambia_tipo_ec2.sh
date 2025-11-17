#!/bin/bash

# Aborto el script si cualquier comando falla
set -e

# --- 1. Compruebo parámetros, incluyendo nociones de los parámetros si el usuario los introduce mal ---
if [ "$#" -ne 2 ]; then
    echo "Error: Número incorrecto de parámetros."
    echo "Uso: $0 <ID_INSTANCIA> <NUEVO_TIPO_INSTANCIA>"
    echo "Ejemplo: $0 i-02d162da757f64b65 t3.small"
    exit 1
fi

# Asigno variables para aclarar
INSTANCE_ID="$1"
NEW_TYPE="$2"

echo "--- Iniciando cambio de tipo para la instancia: $INSTANCE_ID ---"

# --- 2. Comprobar que la instancia existe ---
echo "Verificando la instancia..."

# Intento obtener los datos
# Con 2>/dev/null oculto el error si no la encuentra y lo gestiono yo
INSTANCE_DATA=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0]" --output json 2>/dev/null)

if [ -z "$INSTANCE_DATA" ]; then
    echo "Error: La instancia '$INSTANCE_ID' no existe o no tienes permisos para verla."
    exit 1
fi

# --- 3. Obtengo el estado y el tipo en uso ---
# Uso 'text' como output para que sea fácil de meter en variables
CURRENT_TYPE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].InstanceType" --output text)
CURRENT_STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].State.Name" --output text)

echo "Info: La instancia está actualmente '$CURRENT_STATE' y es de tipo '$CURRENT_TYPE'."

# --- 4. Comprobar si el tipo es el mismo ---
if [ "$CURRENT_TYPE" == "$NEW_TYPE" ]; then
    echo "Información: La instancia ya es de tipo '$NEW_TYPE'. No se requiere acción."
    exit 0
fi

# --- 5. Confirmar con el usuario ---
echo "¡Atención! Este proceso necesita detener la instancia $INSTANCE_ID para cambiarla a '$NEW_TYPE'."
read -p "¿Deseas continuar? (s/n): " -r response
# ^[sSyY]$ comprueba si la respuesta es 's', 'S', 'y' o 'Y'
if [[ ! "$response" =~ ^[sSyY]$ ]]; then
    echo "Proceso abortado por el usuario."
    exit 0
fi

# --- 6. Parar la instancia (si está en ejecución) ---
if [ "$CURRENT_STATE" == "running" ]; then
    echo "Deteniendo la instancia..."
    aws ec2 stop-instances --instance-ids "$INSTANCE_ID" > /dev/null
    
    # --- 7. Esperar a que la instancia esté detenida ---
    echo "Esperando a que la instancia se detenga por completo..."
    aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
    echo "Instancia detenida."

elif [ "$CURRENT_STATE" == "stopped" ]; then
    echo "La instancia ya estaba detenida."
else
    echo "La instancia está en un estado '$CURRENT_STATE', no se puede proceder."
    exit 1
fi

# --- 8. Cambiar el tipo de la instancia ---
echo "Cambiando el tipo de '$CURRENT_TYPE' a '$NEW_TYPE'..."
aws ec2 modify-instance-attribute --instance-id "$INSTANCE_ID" --instance-type "{\"Value\": \"$NEW_TYPE\"}"

# --- 9. Arrancar la instancia ---
echo "Iniciando la instancia con el nuevo tipo..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" > /dev/null

# --- 10. Esperar hasta que esté arrancada ---
echo "Esperando a que la instancia esté en ejecución..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# --- 11. Mensaje de éxito  ---
echo ""
echo "--- ¡Proceso completado con éxito! ---"
echo "La instancia $INSTANCE_ID ahora es de tipo $NEW_TYPE y está en ejecución."