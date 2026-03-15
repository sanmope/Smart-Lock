variable "region" {
  default = "us-east-1"
}

variable "project" {
  default = "smartlock"
}

variable "db_username" {
  default = "smartlock"
}

variable "db_password" {
  default   = "smartlock2024"
  sensitive = true
}

variable "my_ip" {
  description = "Your public IP for SSH/Kafka access (e.g. 203.0.113.10/32). Leave empty to auto-detect."
  default     = ""
}

variable "key_pair_name" {
  description = "Name of an existing EC2 key pair for SSH access"
  type        = string
}
