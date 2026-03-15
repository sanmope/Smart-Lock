terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# ---------------------------------------------------------
# Auto-detect public IP if not provided
# ---------------------------------------------------------
data "http" "my_ip" {
  count = var.my_ip == "" ? 1 : 0
  url   = "https://checkip.amazonaws.com"
}

locals {
  my_cidr = var.my_ip != "" ? var.my_ip : "${chomp(data.http.my_ip[0].response_body)}/32"
}

# ---------------------------------------------------------
# Default VPC and subnets
# ---------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------------------------------------------------------
# Security Group — Kafka EC2
# ---------------------------------------------------------
resource "aws_security_group" "kafka" {
  name        = "${var.project}-kafka-sg"
  description = "Kafka broker + Kafka UI access"
  vpc_id      = data.aws_vpc.default.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [local.my_cidr]
  }

  # Kafka broker
  ingress {
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = [local.my_cidr]
  }

  # Kafka UI
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [local.my_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-kafka-sg" }
}

# ---------------------------------------------------------
# Security Group — RDS
# ---------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${var.project}-rds-sg"
  description = "PostgreSQL access from local + EC2"
  vpc_id      = data.aws_vpc.default.id

  # From your machine
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [local.my_cidr]
  }

  # From Kafka EC2 (consumer runs locally but just in case)
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.kafka.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-rds-sg" }
}

# ---------------------------------------------------------
# EC2 — Kafka (KRaft) + Kafka UI
# ---------------------------------------------------------
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "kafka" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t2.micro"
  key_name               = var.key_pair_name
  vpc_security_group_ids = [aws_security_group.kafka.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Install Docker
    yum update -y
    yum install -y docker
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ec2-user

    # Install Docker Compose plugin
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    # Get public IP for Kafka advertised listeners
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

    # Create docker-compose for Kafka
    mkdir -p /home/ec2-user/kafka
    cat > /home/ec2-user/kafka/docker-compose.yml <<'COMPOSE'
    services:
      kafka:
        image: confluentinc/cp-kafka:7.6.0
        hostname: kafka
        ports:
          - "9092:9092"
        environment:
          KAFKA_NODE_ID: 1
          KAFKA_PROCESS_ROLES: broker,controller
          KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
          KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
          KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
          KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
          KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
          KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
          KAFKA_LOG_RETENTION_HOURS: 168
          KAFKA_HEAP_OPTS: "-Xmx512m -Xms512m"
          CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk
        volumes:
          - kafka-data:/var/lib/kafka/data
        healthcheck:
          test: kafka-broker-api-versions --bootstrap-server localhost:9092
          interval: 15s
          timeout: 10s
          retries: 10

      kafka-init:
        image: confluentinc/cp-kafka:7.6.0
        depends_on:
          kafka:
            condition: service_healthy
        entrypoint: ["/bin/bash", "-c"]
        command:
          - |
            kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists \
              --topic smartlock.lock.status-changes --partitions 12 \
              --config retention.ms=604800000
            kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists \
              --topic smartlock.security.events --partitions 12 \
              --config retention.ms=2592000000
            kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists \
              --topic smartlock.lock.location-updates --partitions 24 \
              --config retention.ms=259200000
            kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists \
              --topic smartlock.shipment.status-changes --partitions 6 \
              --config retention.ms=1209600000
            echo "Topics created."

      kafka-ui:
        image: provectuslabs/kafka-ui:latest
        ports:
          - "8080:8080"
        environment:
          KAFKA_CLUSTERS_0_NAME: smartlock
          KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
        depends_on:
          kafka:
            condition: service_healthy
        deploy:
          resources:
            limits:
              memory: 256m

    volumes:
      kafka-data:
    COMPOSE

    # Fix advertised listeners with actual public IP
    sed -i "s|KAFKA_ADVERTISED_LISTENERS:.*|KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://$PUBLIC_IP:9092|" \
      /home/ec2-user/kafka/docker-compose.yml

    chown -R ec2-user:ec2-user /home/ec2-user/kafka

    # Start Kafka
    cd /home/ec2-user/kafka
    docker compose up -d
  EOF

  tags = { Name = "${var.project}-kafka" }
}

# ---------------------------------------------------------
# RDS — PostgreSQL (2 databases via provisioner)
# ---------------------------------------------------------
resource "aws_db_instance" "postgres" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = "16.13"
  instance_class = "db.t3.micro"

  allocated_storage = 20
  storage_type      = "gp2"

  db_name  = "smartlock"
  username = var.db_username
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = true
  skip_final_snapshot    = true

  tags = { Name = "${var.project}-db" }
}

# Create the second database (smartlock_dw) after RDS is up
resource "null_resource" "create_dw_db" {
  depends_on = [aws_db_instance.postgres]

  provisioner "local-exec" {
    command = "PGPASSWORD=${var.db_password} psql -h ${aws_db_instance.postgres.address} -U ${var.db_username} -d smartlock -c 'CREATE DATABASE smartlock_dw;' 2>/dev/null || true"
  }
}

# ---------------------------------------------------------
# S3 — Spark staging bucket
# ---------------------------------------------------------
resource "aws_s3_bucket" "staging" {
  bucket        = "${var.project}-staging-${data.aws_vpc.default.id}"
  force_destroy = true

  tags = { Name = "${var.project}-staging" }
}

resource "aws_s3_bucket_public_access_block" "staging" {
  bucket = aws_s3_bucket.staging.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
