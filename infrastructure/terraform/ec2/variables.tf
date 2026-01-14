# APEX TRADER - EC2 Variables
# Separated for cleaner configuration management

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"
  
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be one of: production, staging, development."
  }
}

variable "instance_type" {
  description = "EC2 instance type - t3.medium recommended for trading engine"
  type        = string
  default     = "t3.medium"
}

variable "key_name" {
  description = "Name of existing SSH key pair (create in AWS Console: EC2 > Key Pairs)"
  type        = string
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed for SSH access (restrict in production!)"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # CHANGE THIS to your IP in production
}

# =============================================
# DATABASE CONFIGURATION
# =============================================

variable "mongodb_uri" {
  description = "MongoDB connection string (use MongoDB Atlas for production)"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "apex_trader"
}

# =============================================
# POLYMARKET API CREDENTIALS
# =============================================

variable "polymarket_api_key" {
  description = "Polymarket CLOB API key"
  type        = string
  sensitive   = true
}

variable "polymarket_api_secret" {
  description = "Polymarket CLOB API secret"
  type        = string
  sensitive   = true
}

variable "polymarket_api_passphrase" {
  description = "Polymarket CLOB API passphrase"
  type        = string
  sensitive   = true
}

variable "wallet_private_key" {
  description = "Ethereum wallet private key for trading (⚠️ Keep secure!)"
  type        = string
  sensitive   = true
}

# =============================================
# OPTIONAL INTEGRATIONS
# =============================================

variable "sendgrid_api_key" {
  description = "SendGrid API key for email alerts (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "finnhub_api_key" {
  description = "Finnhub API key for sentiment analysis (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alert_email" {
  description = "Email address for trading alerts"
  type        = string
  default     = ""
}

# =============================================
# TRADING CONFIGURATION
# =============================================

variable "initial_capital" {
  description = "Starting capital in USD"
  type        = number
  default     = 1000
}

variable "kelly_fraction" {
  description = "Kelly Criterion fraction (0.1-0.5 recommended)"
  type        = number
  default     = 0.25
  
  validation {
    condition     = var.kelly_fraction >= 0.1 && var.kelly_fraction <= 0.5
    error_message = "Kelly fraction should be between 0.1 and 0.5."
  }
}

variable "max_drawdown_pct" {
  description = "Maximum allowed drawdown percentage"
  type        = number
  default     = 3
}

variable "trades_per_10min" {
  description = "Maximum trades per 10 minutes"
  type        = number
  default     = 500
}

# =============================================
# DOMAIN & SSL (Optional)
# =============================================

variable "domain_name" {
  description = "Domain name for SSL certificate (optional, requires Route53)"
  type        = string
  default     = ""
}

variable "enable_ssl" {
  description = "Enable Let's Encrypt SSL (requires domain_name)"
  type        = bool
  default     = false
}
