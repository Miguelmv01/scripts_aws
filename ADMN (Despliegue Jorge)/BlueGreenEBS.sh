#!/bin/bash

# --- CONFIGURACIÓN ---
APP_NAME="BlueGreenApp"
BUCKET_NAME="eb-bluegreen-test-$(date +%s)"
REGION="us-east-1" 
PLATFORM="64bit Amazon Linux 2023 v4.7.8 running PHP 8.2"

# CONFIGURACIÓN DE LABORATORIO (AÑADIDO)
INSTANCE_PROFILE="LabInstanceProfile"
KEY_PAIR="vockey"

# Nombres de los entornos
ENV_BLUE="bluegreen2"
ENV_GREEN="bluegreen2-green"

# --- 1. PREPARACIÓN DE ARCHIVOS ---
echo "--- 1. Generando versiones HTML y ZIP ---"

# Versión 1.0.0 (AZUL)
echo '<html><body style="background-color:blue; color:white; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;"><h1>Hola Mundo (versión 1.0.0 - Azul)</h1></body></html>' > index.html
zip v1.zip index.html

# Versión 1.0.1 (VERDE)
echo '<html><body style="background-color:green; color:white; display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif;"><h1>Hola Mundo (versión 1.0.1 - Verde)</h1></body></html>' > index.html
zip v2.zip index.html

rm index.html

# --- 2. S3 ---
echo "--- 2. Subiendo a S3 ---"
aws s3 mb s3://$BUCKET_NAME --region $REGION
aws s3 cp v1.zip s3://$BUCKET_NAME/v1.zip
aws s3 cp v2.zip s3://$BUCKET_NAME/v2.zip

# --- 3. APLICACIÓN ---
echo "--- 3. Creando App y Versiones ---"
aws elasticbeanstalk create-application --application-name $APP_NAME --region $REGION

aws elasticbeanstalk create-application-version \
    --application-name $APP_NAME --version-label "v1.0.0" \
    --source-bundle S3Bucket=$BUCKET_NAME,S3Key=v1.zip --region $REGION

aws elasticbeanstalk create-application-version \
    --application-name $APP_NAME --version-label "v1.0.1" \
    --source-bundle S3Bucket=$BUCKET_NAME,S3Key=v2.zip --region $REGION

# --- 4. ENTORNO AZUL (CON ROL Y KEY) ---
echo "--- 4. Lanzando Entorno AZUL (v1.0.0) con LabInstanceProfile... ---"

aws elasticbeanstalk create-environment \
    --application-name $APP_NAME \
    --environment-name $ENV_BLUE \
    --solution-stack-name "$PLATFORM" \
    --version-label "v1.0.0" \
    --region $REGION \
    --option-settings Namespace=aws:autoscaling:launchconfiguration,OptionName=IamInstanceProfile,Value=$INSTANCE_PROFILE \
                      Namespace=aws:autoscaling:launchconfiguration,OptionName=EC2KeyName,Value=$KEY_PAIR

echo "Esperando a que AZUL esté listo..."
aws elasticbeanstalk wait environment-exists --environment-names $ENV_BLUE --region $REGION

# --- 5. ENTORNO VERDE (CON ROL Y KEY) ---
echo "--- 5. Lanzando Entorno VERDE (v1.0.1) con LabInstanceProfile... ---"

aws elasticbeanstalk create-environment \
    --application-name $APP_NAME \
    --environment-name $ENV_GREEN \
    --solution-stack-name "$PLATFORM" \
    --version-label "v1.0.1" \
    --region $REGION \
    --option-settings Namespace=aws:autoscaling:launchconfiguration,OptionName=IamInstanceProfile,Value=$INSTANCE_PROFILE \
                      Namespace=aws:autoscaling:launchconfiguration,OptionName=EC2KeyName,Value=$KEY_PAIR

echo "Esperando a que VERDE esté listo..."
aws elasticbeanstalk wait environment-exists --environment-names $ENV_GREEN --region $REGION

# --- 6. SWAP ---
echo "--- 6. Realizando SWAP de CNAMEs ---"
read -p "Presiona ENTER para intercambiar el tráfico..."

aws elasticbeanstalk swap-environment-cnames \
    --source-environment-name $ENV_BLUE \
    --destination-environment-name $ENV_GREEN \
    --region $REGION

echo "--- ¡PROCESO FINALIZADO! ---"