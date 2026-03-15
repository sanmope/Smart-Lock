output "kafka_public_ip" {
  description = "Kafka EC2 public IP"
  value       = aws_instance.kafka.public_ip
}

output "kafka_bootstrap" {
  description = "Kafka bootstrap servers (for KAFKA_BOOTSTRAP_SERVERS env var)"
  value       = "${aws_instance.kafka.public_ip}:9092"
}

output "kafka_ui_url" {
  description = "Kafka UI URL"
  value       = "http://${aws_instance.kafka.public_ip}:8080"
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_address" {
  description = "RDS hostname only"
  value       = aws_db_instance.postgres.address
}

output "database_url" {
  description = "DATABASE_URL for the API and consumer"
  value       = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/smartlock"
  sensitive   = true
}

output "redshift_jdbc_url" {
  description = "JDBC URL for Spark -> Redshift (smartlock_dw database)"
  value       = "jdbc:postgresql://${aws_db_instance.postgres.address}:5432/smartlock_dw"
}

output "s3_bucket" {
  description = "S3 staging bucket name"
  value       = aws_s3_bucket.staging.id
}

output "s3_staging_path" {
  description = "S3 staging path for Spark"
  value       = "s3a://${aws_s3_bucket.staging.id}"
}

output "ssh_command" {
  description = "SSH into the Kafka instance"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ec2-user@${aws_instance.kafka.public_ip}"
}

# --- docker-compose overrides ---
output "local_env" {
  description = "Environment variables to set for local docker-compose"
  value       = <<-EOT

    # Add these to docker-compose.yml or a .env file:
    KAFKA_BOOTSTRAP_SERVERS=${aws_instance.kafka.public_ip}:9092
    DATABASE_URL=postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/smartlock

  EOT
  sensitive   = true
}
