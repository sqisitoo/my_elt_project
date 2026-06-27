resource "random_password" "rds_password" {
  length  = 16
  special = false
}

resource "aws_secretsmanager_secret" "rds_password_secret" {
  name                    = "airflow-rds-password"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "rds_password_value" {
  secret_id     = aws_secretsmanager_secret.rds_password_secret.id
  secret_string = random_password.rds_password.result
}

resource "aws_security_group" "rds_sg" {
  name        = "airflow-rds-sg"
  description = "Allow inbound traffic to Postgres"
  vpc_id      = aws_vpc.airflow.id

  dynamic "ingress" {
    for_each = var.create_bastion ? [1] : []
    content {
      description     = "Postgres from Bastion"
      from_port       = 5432
      to_port         = 5432
      protocol        = "tcp"
      security_groups = [aws_security_group.bastion_sg[0].id]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "airflow-rds-sg"
  }
}

resource "aws_db_subnet_group" "airflow" {
  name       = "airflow-db-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "airflo-db-subnet-group"
  }
}

resource "aws_db_instance" "default" {
  identifier = "airflow-postgres-db"

  storage_encrypted          = true
  auto_minor_version_upgrade = true

  engine            = "postgres"
  engine_version    = "17.7"
  instance_class    = "db.t4g.micro"
  allocated_storage = 20

  db_name  = "airflow_db"
  username = "airflow_user"
  password = aws_secretsmanager_secret_version.rds_password_value.secret_string

  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.airflow.name
  publicly_accessible    = false

  skip_final_snapshot = true

  deletion_protection = false
}