import boto3
import time
import sys
from botocore.exceptions import ClientError

# --- CONFIGURACIÓN ---
REGION_1 = 'us-east-1' 
REGION_2 = 'us-west-2' 

ASN_EAST = 64512
ASN_WEST = 64513

ec2_east = boto3.resource('ec2', region_name=REGION_1)
client_east = boto3.client('ec2', region_name=REGION_1)
ec2_west = boto3.resource('ec2', region_name=REGION_2)
client_west = boto3.client('ec2', region_name=REGION_2)

sts = boto3.client('sts')
MY_ACCOUNT_ID = sts.get_caller_identity()['Account']

def log(msg):
    print(f"[TGW-MULTI] {msg}")

# --- FUNCIÓN DE SEGURIDAD PARA RUTAS ---
def create_route_with_retry(client, destination, tgw_rt_id, attach_id):
    """Intenta crear la ruta y reintenta si el attachment no está listo (IncorrectState)"""
    max_retries = 10
    for i in range(max_retries):
        try:
            client.create_transit_gateway_route(
                DestinationCidrBlock=destination,
                TransitGatewayRouteTableId=tgw_rt_id,
                TransitGatewayAttachmentId=attach_id
            )
            log(f"Ruta creada hacia {destination}.")
            return
        except ClientError as e:
            code = e.response['Error']['Code']
            if code == 'IncorrectState' or code == 'InvalidTransitGatewayAttachmentID.NotFound':
                log(f"El Attachment aún no está listo para enrutar ({code}). Reintentando en 15s... ({i+1}/{max_retries})")
                time.sleep(15)
            else:
                raise e # Si es otro error, fallar de verdad
    raise Exception("No se pudo crear la ruta tras múltiples intentos.")

def create_vpc_stack(ec2_res, client, cidr, name):
    log(f"Creando VPC {name} ({cidr})...")
    vpc = ec2_res.create_vpc(CidrBlock=cidr)
    vpc.create_tags(Tags=[{"Key": "Name", "Value": name}])
    vpc.wait_until_available()
    az = client.describe_availability_zones()['AvailabilityZones'][0]['ZoneName']
    subnet = vpc.create_subnet(CidrBlock=cidr.replace("0.0/16", "1.0/24"), AvailabilityZone=az)
    subnet.create_tags(Tags=[{"Key": "Name", "Value": f"Subnet-{name}"}])
    return vpc, subnet

def main():
    try:
        log("--- INICIANDO DESPLIEGUE TGW MULTI-REGION (FIXED) ---")

        # 1. CREAR VPCs
        vpc_east_1, sub_east_1 = create_vpc_stack(ec2_east, client_east, '10.1.0.0/16', 'VPC-R1-A')
        vpc_east_2, sub_east_2 = create_vpc_stack(ec2_east, client_east, '10.2.0.0/16', 'VPC-R1-B')
        vpc_west_1, sub_west_1 = create_vpc_stack(ec2_west, client_west, '10.3.0.0/16', 'VPC-R2-C')

        # 2. CREAR TGWs
        log(f"Creando TGW en {REGION_1}...")
        tgw_east = client_east.create_transit_gateway(
            Options={'AmazonSideAsn': ASN_EAST, 'AutoAcceptSharedAttachments': 'enable'},
            TagSpecifications=[{'ResourceType': 'transit-gateway', 'Tags': [{'Key': 'Name', 'Value': 'TGW-East'}]}]
        )['TransitGateway']
        
        log(f"Creando TGW en {REGION_2}...")
        tgw_west = client_west.create_transit_gateway(
            Options={'AmazonSideAsn': ASN_WEST, 'AutoAcceptSharedAttachments': 'enable'},
            TagSpecifications=[{'ResourceType': 'transit-gateway', 'Tags': [{'Key': 'Name', 'Value': 'TGW-West'}]}]
        )['TransitGateway']

        log("Esperando TGWs available (~2 min)...")
        while True:
            te = client_east.describe_transit_gateways(TransitGatewayIds=[tgw_east['TransitGatewayId']])['TransitGateways'][0]
            tw = client_west.describe_transit_gateways(TransitGatewayIds=[tgw_west['TransitGatewayId']])['TransitGateways'][0]
            if te['State'] == 'available' and tw['State'] == 'available':
                break
            time.sleep(15)

        # 3. ATTACHMENTS
        log("Adjuntando VPCs...")
        client_east.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw_east['TransitGatewayId'], VpcId=vpc_east_1.id, SubnetIds=[sub_east_1.id])
        client_east.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw_east['TransitGatewayId'], VpcId=vpc_east_2.id, SubnetIds=[sub_east_2.id])
        client_west.create_transit_gateway_vpc_attachment(TransitGatewayId=tgw_west['TransitGatewayId'], VpcId=vpc_west_1.id, SubnetIds=[sub_west_1.id])

        log("Esperando estabilización de attachments (40s)...")
        time.sleep(40) 

        # 4. PEERING
        log("Creando Peering Cross-Region...")
        peer_att = client_east.create_transit_gateway_peering_attachment(
            TransitGatewayId=tgw_east['TransitGatewayId'],
            PeerTransitGatewayId=tgw_west['TransitGatewayId'],
            PeerAccountId=MY_ACCOUNT_ID,
            PeerRegion=REGION_2,
            TagSpecifications=[{'ResourceType': 'transit-gateway-attachment', 'Tags': [{'Key': 'Name', 'Value': 'Peering-East-West'}]}]
        )['TransitGatewayPeeringAttachment']
        
        peer_id = peer_att['TransitGatewayAttachmentId']
        log(f"Peering ID: {peer_id}. Esperando propagación para aceptar...")
        
        time.sleep(15) # Espera inicial
        accepted = False
        while not accepted:
            try:
                client_west.accept_transit_gateway_peering_attachment(TransitGatewayAttachmentId=peer_id)
                accepted = True
                log("Peering Aceptado!")
            except Exception:
                log("Aún no llegó la solicitud al Oeste... reintentando en 10s")
                time.sleep(10)
        
        log("Esperando estado 'available' del peering...")
        while True:
            p_state = client_east.describe_transit_gateway_peering_attachments(TransitGatewayAttachmentIds=[peer_id])['TransitGatewayPeeringAttachments'][0]['State']
            if p_state == 'available':
                break
            time.sleep(10)

        # 5. RUTAS (SECCIÓN FIXEADA CON REINTENTOS)
        log("Configurando Rutas de VPC...")
        for vpc in [vpc_east_1, vpc_east_2]:
            rt = list(vpc.route_tables.all())[0]
            rt.create_route(DestinationCidrBlock='10.3.0.0/16', TransitGatewayId=tgw_east['TransitGatewayId'])
            
        rt_west = list(vpc_west_1.route_tables.all())[0]
        rt_west.create_route(DestinationCidrBlock='10.1.0.0/16', TransitGatewayId=tgw_west['TransitGatewayId'])
        rt_west.create_route(DestinationCidrBlock='10.2.0.0/16', TransitGatewayId=tgw_west['TransitGatewayId'])

        log("Configurando Rutas Internas TGW (Con lógica de reintento)...")
        
        # Ruta en TGW Este
        te_rt_id = client_east.describe_transit_gateways(TransitGatewayIds=[tgw_east['TransitGatewayId']])['TransitGateways'][0]['Options']['AssociationDefaultRouteTableId']
        create_route_with_retry(client_east, '10.3.0.0/16', te_rt_id, peer_id)

        # Ruta en TGW Oeste
        tw_rt_id = client_west.describe_transit_gateways(TransitGatewayIds=[tgw_west['TransitGatewayId']])['TransitGateways'][0]['Options']['AssociationDefaultRouteTableId']
        create_route_with_retry(client_west, '10.0.0.0/8', tw_rt_id, peer_id)

        print("\n" + "="*50)
        print("DESPLIEGUE EXITOSO")
        print("="*50)
        print(f"Peering ID para borrar (Blackhole): {peer_id}")
        print("="*50)

    except Exception as e:
        print(f"[ERROR FATAL] {e}")

if __name__ == '__main__':
    main()