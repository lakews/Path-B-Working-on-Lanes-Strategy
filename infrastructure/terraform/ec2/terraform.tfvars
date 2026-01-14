# AWS Configuration
aws_region    = "us-east-1"
environment   = "production"
instance_type = "t2.micro"
key_name      = "apex-key"

# SSH Access - Restrict to your IP for security (0.0.0.0/0 = open to all)
allowed_ssh_cidrs = ["0.0.0.0/0"]

# Database - MongoDB on EC2 (localhost)
mongodb_uri = "mongodb://localhost:27017"
db_name     = "apex_trader"

# Polymarket API
polymarket_api_key        = "strategybot-10"
polymarket_api_secret     = "HgPWwvXJal5m_R-n-j_jZLseV_9CfKK2ziaCHVfPgm0="
polymarket_api_passphrase = "223b50aeb64a7b3b25a2b7d902f0506606d18a12a93af3cc411cf0a980f88e2c"

# Wallet - Leave empty if not doing live trading yet
wallet_private_key = ""

# Trading Config
initial_capital  = 1000
kelly_fraction   = 0.25
max_drawdown_pct = 3
trades_per_10min = 500

# Optional integrations
sendgrid_api_key = ""
finnhub_api_key  = "ctv8lchr01qhb9btfpt0ctv8lchr01qhb9btfptg"
alert_email      = ""

# Domain (leave empty for IP-based access)
domain_name = ""
enable_ssl  = false
