# Despliegue Básico en AWS con Terraform

Este repositorio contiene un archivo de configuración de Terraform (`plantilla1.tf`) para desplegar infraestructura básica en la región `us-east-1` de AWS.

## Recursos que despliega:
1. **VPC**: Red virtual propia con el bloque CIDR `10.0.0.0/16`.
2. **Subred**: Ubicada en la zona `us-east-1a` con el bloque CIDR `10.0.1.0/24`.
3. **Grupo de Seguridad**: Configurado para permitir tráfico de entrada TCP por el puerto 80 a nivel global (`0.0.0.0/0`).
4. **Instancia EC2**: Máquina tipo `t2.micro` que se asocia automáticamente a la subred y al grupo de seguridad creados. Además, se le asigna una IP pública de forma automática al crearse.