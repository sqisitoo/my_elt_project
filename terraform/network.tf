resource "aws_vpc" "airflow" {
  cidr_block = "10.0.0.0/16"

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "airflow-vpc"
  }
}

resource "aws_internet_gateway" "airflow" {
  vpc_id = aws_vpc.airflow.id

  tags = {
    Name = "airflow-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.airflow.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.airflow.id
  }

  tags = {
    Name = "airflow-public-rt"
  }
}

resource "aws_subnet" "public_1" {
  vpc_id = aws_vpc.airflow.id

  cidr_block = "10.0.1.0/24"

  availability_zone = "eu-north-1a"

  map_public_ip_on_launch = true

  tags = {
    Name = "airflow-public-subnet-1"
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_subnet" "public_2" {
  vpc_id = aws_vpc.airflow.id

  cidr_block = "10.0.2.0/24"

  availability_zone = "eu-north-1b"

  map_public_ip_on_launch = true

  tags = {
    Name = "airflow-public-subnet-2"
  }
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}


resource "aws_subnet" "private_1" {
  vpc_id = aws_vpc.airflow.id

  cidr_block = "10.0.3.0/24"

  availability_zone = "eu-north-1a"

  map_public_ip_on_launch = false
}

resource "aws_subnet" "private_2" {
  vpc_id = aws_vpc.airflow.id

  cidr_block = "10.0.4.0/24"

  availability_zone = "eu-north-1b"

  map_public_ip_on_launch = false
}
