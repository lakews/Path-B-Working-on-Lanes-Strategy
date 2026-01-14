# APEX TRADER - EC2 Outputs
# Connection and access information after deployment

output "public_ip" {
  description = "Public IP address of the APEX TRADER server"
  value       = aws_eip.apex_trader.public_ip
}

output "public_dns" {
  description = "Public DNS name of the EC2 instance"
  value       = aws_instance.apex_trader.public_dns
}

output "instance_id" {
  description = "EC2 Instance ID (for AWS Console reference)"
  value       = aws_instance.apex_trader.id
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_eip.apex_trader.public_ip}"
}

output "frontend_url" {
  description = "APEX TRADER Dashboard URL"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_eip.apex_trader.public_ip}"
}

output "backend_api_url" {
  description = "Backend API URL"
  value       = var.domain_name != "" ? "https://${var.domain_name}/api" : "http://${aws_eip.apex_trader.public_ip}/api"
}

output "websocket_url" {
  description = "WebSocket URL for real-time updates"
  value       = var.domain_name != "" ? "wss://${var.domain_name}/ws" : "ws://${aws_eip.apex_trader.public_ip}/ws"
}

output "setup_log_command" {
  description = "Command to view setup logs on the server"
  value       = "sudo tail -f /var/log/apex-trader-setup.log"
}

output "service_status_command" {
  description = "Command to check service status"
  value       = "sudo systemctl status apex-backend apex-frontend nginx"
}

# Security reminders
output "security_reminders" {
  description = "Important security tasks after deployment"
  value       = <<-EOT
    
    ⚠️  SECURITY REMINDERS:
    
    1. Restrict SSH access in terraform.tfvars:
       allowed_ssh_cidrs = ["YOUR_IP/32"]
    
    2. Enable SSL for production:
       enable_ssl  = true
       domain_name = "your-domain.com"
    
    3. Backup your private keys securely
    
    4. Monitor CloudWatch alarms for CPU/status checks
    
  EOT
}
