resource "random_password" "rds_password" {
  length = 16
  # do not change
  # airflow create url connection string
  # with special symbols it will be broken
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

# Rules for this group are standalone aws_security_group_rule resources (see ecs.tf).
# Do not add inline ingress/egress blocks here: the AWS provider does not support mixing
# the two styles on one group, and they overwrite each other on apply. No egress rule is
# needed — security groups are stateful and Postgres initiates nothing outbound.
resource "aws_security_group" "rds_sg" {
  name        = "airflow-rds-sg"
  description = "Allow inbound traffic to Postgres"
  vpc_id      = aws_vpc.airflow.id

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

  engine = "postgres"
  # Major version only. An exact pin ("17.7") drifts against auto_minor_version_upgrade:
  # AWS upgrades the instance, the config still demands the old minor, and the next apply
  # fails because a downgrade is impossible.
  engine_version    = "17"
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