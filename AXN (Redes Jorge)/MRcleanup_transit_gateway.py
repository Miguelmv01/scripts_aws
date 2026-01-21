#!/usr/bin/env python3
import boto3
import time

def cleanup_transit_gateway_infrastructure():
    """Elimina las conexiones intra-regionales Transit Gateway (VPC attachments) y VPCs asociadas.
    Mantiene los Transit Gateways y el peering inter-regional."""
    ec2_east = boto3.client('ec2', region_name='us-east-1')
    ec2_west = boto3.client('ec2', region_name='us-west-2')
    
    print("=== Limpiando conexiones intra-regionales Transit Gateway ===")
    
    try:
        # Nota: Este script ahora solo elimina conexiones intra-regionales (VPC attachments)
        # Las conexiones inter-regionales (TGW peering) se mantienen
        
        # 1. Eliminar TGW Attachments y VPCs por región (conexiones intra-regionales)
        regions = [
            ('us-east-1', ec2_east, ['VPC-East-1', 'VPC-East-2']),
            ('us-west-2', ec2_west, ['VPC-West-1', 'VPC-West-2'])
        ]
        
        for region, ec2_client, vpc_names in regions:
            print(f"\n--- Limpiando recursos en {region} ---")
            
            # Obtener TGW ID
            try:
                tgws = ec2_client.describe_transit_gateways()
                for tgw in tgws['TransitGateways']:
                    if tgw['State'] in ['available', 'pending']:
                        tgw_id = tgw['TransitGatewayId']
                        
                        # Eliminar VPC attachments
                        attachments = ec2_client.describe_transit_gateway_vpc_attachments(
                            Filters=[{'Name': 'transit-gateway-id', 'Values': [tgw_id]}]
                        )
                        
                        attachment_ids = []
                        for attachment in attachments['TransitGatewayVpcAttachments']:
                            if attachment['State'] in ['available', 'pending']:
                                attachment_id = attachment['TransitGatewayAttachmentId']
                                attachment_ids.append(attachment_id)
                                print(f"Eliminando attachment: {attachment_id}")
                                ec2_client.delete_transit_gateway_vpc_attachment(TransitGatewayAttachmentId=attachment_id)
                        
                        # Esperar eliminación de attachments
                        if attachment_ids:
                            print("Esperando eliminación de attachments...")
                            for att_id in attachment_ids:
                                while True:
                                    try:
                                        response = ec2_client.describe_transit_gateway_vpc_attachments(TransitGatewayAttachmentIds=[att_id])
                                        state = response['TransitGatewayVpcAttachments'][0]['State']
                                        if state in ['deleted', 'deleting']:
                                            break
                                    except:
                                        break  # Attachment no existe
                                    time.sleep(15)
            except Exception as e:
                print(f"Error eliminando attachments en {region}: {e}")
            
            # Eliminar VPCs específicas
            for vpc_name in vpc_names:
                try:
                    vpcs = ec2_client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
                    
                    for vpc in vpcs['Vpcs']:
                        vpc_id = vpc['VpcId']
                        print(f"Limpiando {vpc_name}: {vpc_id}")
                        
                        # Terminar instancias
                        instances = ec2_client.describe_instances(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
                        instance_ids = []
                        for reservation in instances['Reservations']:
                            for instance in reservation['Instances']:
                                if instance['State']['Name'] not in ['terminated', 'terminating']:
                                    instance_ids.append(instance['InstanceId'])
                                    print(f"Terminando instancia: {instance['InstanceId']}")
                                    ec2_client.terminate_instances(InstanceIds=[instance['InstanceId']])
                        
                        # Esperar terminación
                        if instance_ids:
                            print("Esperando terminación de instancias...")
                            ec2_client.get_waiter('instance_terminated').wait(InstanceIds=instance_ids)
                        
                        # Eliminar Security Groups
                        sgs = ec2_client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
                        for sg in sgs['SecurityGroups']:
                            if sg['GroupName'] != 'default':
                                print(f"Eliminando SG: {sg['GroupId']}")
                                ec2_client.delete_security_group(GroupId=sg['GroupId'])
                        
                        # Eliminar subredes
                        subnets = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
                        for subnet in subnets['Subnets']:
                            print(f"Eliminando subred: {subnet['SubnetId']}")
                            ec2_client.delete_subnet(SubnetId=subnet['SubnetId'])
                        
                        # Desconectar y eliminar IGW
                        igws = ec2_client.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])
                        for igw in igws['InternetGateways']:
                            igw_id = igw['InternetGatewayId']
                            print(f"Desconectando IGW: {igw_id}")
                            ec2_client.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
                            print(f"Eliminando IGW: {igw_id}")
                            ec2_client.delete_internet_gateway(InternetGatewayId=igw_id)
                        
                        # Eliminar VPC
                        print(f"Eliminando VPC: {vpc_id}")
                        ec2_client.delete_vpc(VpcId=vpc_id)
                        
                except Exception as e:
                    print(f"Error eliminando {vpc_name}: {e}")
        
        # 2. Eliminar Transit Gateways (opcional, comentado para mantener TGWs con peering inter-regional)
        # print("\n--- Eliminando Transit Gateways ---")
        # # Pausa adicional para asegurar que todos los attachments estén eliminados
        # time.sleep(60)
        
        # for region, ec2_client, tgw_id in tgw_ids:
        #     try:
        #         print(f"Eliminando TGW {tgw_id} en {region}")
        #         ec2_client.delete_transit_gateway(TransitGatewayId=tgw_id)
                
        #         # Esperar eliminación del TGW
        #         print(f"Esperando eliminación de TGW {tgw_id}...")
        #         while True:
        #             try:
        #                 response = ec2_client.describe_transit_gateways(TransitGatewayIds=[tgw_id])
        #                 state = response['TransitGateways'][0]['State']
        #                 if state in ['deleted', 'deleting']:
        #                     break
        #             except:
        #                 break  # TGW no existe, eliminado
        #             time.sleep(30)
                    
        #     except Exception as e:
        #         print(f"Error eliminando TGW {tgw_id}: {e}")
        
        print("\n✅ Limpieza de conexiones intra-regionales completada!")
        
    except Exception as e:
        print(f"❌ Error durante la limpieza: {e}")

def main():
    cleanup_transit_gateway_infrastructure()

if __name__ == "__main__":
    main()