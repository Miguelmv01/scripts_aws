import boto3

def crear_vpc():
    # Crear cliente de EC2
    ec2 = boto3.client('ec2')

    # Crear la VPC
    vpc = ec2.create_vpc(CidrBlock='192.168.5.0/16')
    vpc_id = vpc['Vpc']['VpcId']
    print(f'VPC creada con ID: {vpc_id}')

    # Habilitar DNS support
    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsSupport={'Value': True}
    )

    # Habilitar DNS hostnames
    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsHostnames={'Value': True}
    )

    # Etiquetar la VPC (opcional)
    ec2.create_tags(
        Resources=[vpc_id],
        Tags=[{'Key': 'Name', 'Value': 'MiVPC-Boto3'}]
    )

    print("DNS habilitado y etiqueta 'MiVPC-Boto3' asignada.")
    return vpc_id

if __name__ == "__main__":
    vpc_id_ = crear_vpc()
    print(f'Proceso completado. ID de la VPC: {vpc_id_}')