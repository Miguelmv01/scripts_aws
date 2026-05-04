# Región y proveedor que uso
provider "aws" {
    region = "us-east-1"
}

# 1. Creación de la VPC
resource "aws_vpc" "mi_vpc" {
    cidr_block = "10.0.0.0/16"

    tags = {
        Name = "MiVPC"
    }
}

# 2. Creación de la Subred asociada a la VPC
resource "aws_subnet" "mi_subred" {
    vpc_id            = aws_vpc.mi_vpc.id
    cidr_block        = "10.0.1.0/24"
    availability_zone = "us-east-1a"

    tags = {
        Name = "MiSubred"
    }
}

# 3. Creación de la EC2 asociada a la Subred y al Grupo de Seguridad
resource "aws_instance" "example" {
    ami                    = "ami-0ed094fb1304fd857"
    instance_type          = "t2.micro"
    key_name               = "vockey"
    subnet_id              = aws_subnet.mi_subred.id
    vpc_security_group_ids = [aws_security_group.mi_grupo_seguridad.id]
    associate_public_ip_address = true

    tags = {
        Name = "EC2Instance"
    }
}

resource "aws_security_group" "mi_grupo_seguridad" {
    name        = "prueba-sg-puerto-80"
    description = "SG de prueba con puerto 80 abierto"
    
    # Descomentar para asociarlo a la VPC del paso anterior
    vpc_id      = aws_vpc.mi_vpc.id

    ingress {
        from_port   = 80
        to_port     = 80
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    # Al omitir por completo el bloque "egress", no se creará ninguna regla de salida
}