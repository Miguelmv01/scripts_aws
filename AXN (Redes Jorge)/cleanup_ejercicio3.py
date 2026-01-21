import boto3
import time
from botocore.exceptions import ClientError

# --- CONFIGURACIÓN ---
REGIONS = ['us-east-1', 'us-west-2']
# Nombres de las VPCs que queremos borrar (para no borrar las de otros proyectos)
TAG_NAMES = ['VPC-R1-A', 'VPC-R1-B', 'VPC-R2-C'] 

def log(msg):
    print(f"[CLEANUP-MASTER] {msg}")

def cleanup_region_logic(region):
    log(f"--- CONECTANDO A {region} ---")
    ec2 = boto3.resource('ec2', region_name=region)
    client = boto3.client('ec2', region_name=region)

    # ---------------------------------------------------------
    # 1. ELIMINAR ATTACHMENTS (VPC y PEERING)
    # ---------------------------------------------------------
    # Buscamos attachments que NO estén ya borrados
    atts = client.describe_transit_gateway_attachments(
        Filters=[{'Name': 'state', 'Values': ['available', 'pending', 'pendingAcceptance', 'modifying', 'initiating']}]
    )['TransitGatewayAttachments']

    if atts:
        log(f"Encontrados {len(atts)} attachments activos. Enviando orden de borrado...")
        for att in atts:
            att_id = att['TransitGatewayAttachmentId']
            res_type = att['ResourceType']
            state = att['State']

            log(f" -> Procesando {att_id} ({res_type}) en estado '{state}'")
            
            try:
                # LÓGICA ESPECÍFICA PARA BOTO3 ANTIGUO
                if res_type == 'peering':
                    client.delete_transit_gateway_peering_attachment(TransitGatewayAttachmentId=att_id)
                elif res_type == 'vpc':
                    client.delete_transit_gateway_vpc_attachment(TransitGatewayAttachmentId=att_id)
                else:
                    # Fallback para VPNs u otros
                    client.delete_transit_gateway_attachment(TransitGatewayAttachmentId=att_id)
                log(f"    Orden de borrado enviada.")
            except ClientError as e:
                # Si ya se está borrando o no existe, lo ignoramos
                if "IncorrectState" in str(e) or "NotFound" in str(e):
                    log(f"    Ya se estaba borrando o no existe. Continuamos.")
                else:
                    log(f"    Error no crítico: {e}")

    # ---------------------------------------------------------
    # 2. ESPERA ACTIVA (BLOQUEANTE)
    # ---------------------------------------------------------
    # No avanzamos al TGW hasta que no queden attachments. Punto.
    log("Verificando limpieza de attachments (Loop de espera)...")
    while True:
        try:
            current_atts = client.describe_transit_gateway_attachments(
                Filters=[{'Name': 'state', 'Values': ['available', 'pending', 'deleting', 'modifying', 'pendingAcceptance']}]
            )['TransitGatewayAttachments']
            
            if not current_atts:
                log("¡Todos los attachments han desaparecido!")
                break
            
            # Feedback visual para no desesperar
            count = len(current_atts)
            types = [a['ResourceType'] for a in current_atts]
            log(f"Esperando a AWS... Quedan {count} attachments borrándose ({types})...")
            time.sleep(15)
            
        except Exception as e:
            log(f"Error consultando estado (reintentando): {e}")
            time.sleep(10)

    # ---------------------------------------------------------
    # 3. ELIMINAR TRANSIT GATEWAYS
    # ---------------------------------------------------------
    tgws = client.describe_transit_gateways(
        Filters=[{'Name': 'state', 'Values': ['available', 'pending', 'deleting']}]
    )['TransitGateways']

    for tgw in tgws:
        tgw_id = tgw['TransitGatewayId']
        log(f"Gestionando TGW {tgw_id}...")
        
        # Intentar borrar hasta que nos deje (por si hay latencia en la desaparición de attachments)
        while True:
            try:
                # Verificar estado actual
                res = client.describe_transit_gateways(TransitGatewayIds=[tgw_id])
                if not res['TransitGateways']:
                    break # Ya no existe
                
                state = res['TransitGateways'][0]['State']
                if state == 'deleted':
                    log(f"TGW {tgw_id} ya está eliminado.")
                    break
                
                if state != 'deleting':
                    client.delete_transit_gateway(TransitGatewayId=tgw_id)
                    log(f"Orden de borrado enviada para TGW {tgw_id}.")
                else:
                    log(f"TGW {tgw_id} está en estado 'deleting'. Esperando...")
                
                time.sleep(10)
                
            except ClientError as e:
                if "IncorrectState" in str(e):
                    log("AWS aún detecta dependencias. Reintentando en 10s...")
                    time.sleep(10)
                elif "NotFound" in str(e):
                    break
                else:
                    log(f"Error: {e}. Reintentando...")
                    time.sleep(10)

    # ---------------------------------------------------------
    # 4. ELIMINAR VPCs (Estándar)
    # ---------------------------------------------------------
    log("Limpiando VPCs y dependencias de red...")
    filters = [{'Name': 'tag:Name', 'Values': TAG_NAMES}]
    vpcs = list(ec2.vpcs.filter(Filters=filters))
    
    if not vpcs:
        log("No se encontraron VPCs con los tags del ejercicio.")
    
    for vpc in vpcs:
        log(f"Borrando VPC {vpc.id}...")
        # Borrar Subnets
        for subnet in vpc.subnets.all():
            # Borrar Interfaces de red residuales
            for eni in subnet.network_interfaces.all():
                try: eni.delete()
                except: pass
            try: client.delete_subnet(SubnetId=subnet.id)
            except: pass
            
        # Borrar IGWs
        for igw in vpc.internet_gateways.all():
            try:
                vpc.detach_internet_gateway(InternetGatewayId=igw.id)
                igw.delete()
            except: pass
            
        # Borrar VPC
        try:
            client.delete_vpc(VpcId=vpc.id)
            log("-> VPC Eliminada.")
        except Exception as e:
            log(f"-> Error borrando VPC: {e}")

def main():
    log("INICIANDO PROTOCOLO DE LIMPIEZA UNIVERSAL")
    for r in REGIONS:
        try:
            cleanup_region_logic(r)
        except Exception as e:
            log(f"Error crítico en región {r}: {e}")
    
    log("PROTOCOLO FINALIZADO. INFRAESTRUCTURA LIMPIA.")

if __name__ == '__main__':
    main()