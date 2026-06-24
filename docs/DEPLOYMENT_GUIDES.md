# Deployment Guides

Complete setup instructions for running BY BOTS locally and on cloud hosting.

---

## Table of Contents

1. [Local Deployment](#local-deployment)
2. [Railway.app Deployment](#railwayapp-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Windows Task Scheduler](#windows-task-scheduler)

---

## Local Deployment

Run BY BOTS on your personal computer or server.

### Requirements

- Windows 7+ or Linux/macOS
- Python 3.11+
- 500 MB disk space
- Stable internet connection

### Installation Steps

1. Install Python from python.org (if not already installed)

2. Clone or download the repository

3. Navigate to project directory:
   ```
   cd BY-BOTS
   ```

4. Copy environment template:
   ```
   copy config\.env.example .env
   ```

5. Edit .env with your Discord and Facebook information:
   - DISCORD_TOKEN - Your bot token
   - DISCORD_CHANNEL_ID - Target channel ID
   - FACEBOOK_SOURCES - Facebook URLs to monitor

6. Run setup:
   ```
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```

7. Start the bot:
   ```
   python src/bot.py
   ```

### Using run.bat Menu

On Windows, use the convenient menu:

```
run.bat
```

Select from options:
- Install dependencies
- Run bot
- Run dashboard
- Run both together
- Kill processes
- Test security reminder

### Keeping Bot Running 24/7 Locally

To run continuously when PC is on:

Option A: Windows Task Scheduler
- Create a scheduled task to run run.bat at startup
- See Windows Task Scheduler section below

Option B: Command Line with Keep-Alive
- Use a script or tool like nssm to install as Windows service
- Automatically starts on system boot

Note: Bot will stop when PC shuts down. For true 24/7, use cloud hosting.

---

## Railway.app Deployment

Deploy to Railway.app for 24/7 hosting with free monthly credits.

### Prerequisites

- GitHub account with your code pushed
- Railway.app account (sign up at railway.app)
- Discord bot token and channel IDs from local config

### Step 1: Push Code to GitHub

1. Initialize git locally:
   ```
   git init
   git add .
   git commit -m "Initial commit - BY BOTS"
   git remote add origin https://github.com/USERNAME/REPONAME.git
   git branch -M main
   git push -u origin main
   ```

2. Code is now on GitHub

### Step 2: Create Railway Account

1. Go to https://railway.app/
2. Click "Start Building"
3. Sign up with GitHub (easiest option)
4. Authorize Railway access to your repositories

### Step 3: Create New Project

1. In Railway dashboard, click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your repository
4. Railway automatically detects Dockerfile and begins building

### Step 4: Configure Environment Variables

While deployment is building:

1. Click "Variables" tab
2. Add each variable from your .env file:

   Key: DISCORD_TOKEN
   Value: [your token]

   Key: DISCORD_CHANNEL_ID
   Value: 1514161755700334655

   Continue for all variables in your .env

3. No need to save - Railway applies automatically

### Step 5: Wait for Deployment

1. Go to "Deployments" tab
2. Watch status:
   - Building (blue) - Docker image compiling
   - Running (green) - Bot is online and working
   - Failed (red) - Check logs for errors

Deployment takes 2-5 minutes.

### Step 6: Verify Bot is Online

1. Check Discord server - bot should appear as Online
2. Wait 20 minutes - security reminder should post (if enabled)
3. Monitor logs in Railway Console tab

### Updating Code

Make changes locally and push to GitHub:

```
git add .
git commit -m "Update bot settings"
git push origin main
```

Railway automatically redeploys within 1-2 minutes.

### Costs

- Free tier: 5 USD/month credits
- Most Discord bots use less than 5 USD/month, keeping cost at 0
- Set spending limit in Account settings to avoid overages
- Scale up pay-as-you-go if needed

### Troubleshooting

Build fails with Dockerfile error:
- Ensure Dockerfile does not contain VOLUME instruction
- Railway uses its own volume system
- Remove or comment out VOLUME lines

Build fails with missing variables:
- Verify all required variables are in Variables tab
- Check for typos in variable names
- Redeploy after fixing

Bot logs show Python errors:
- Check logs in Console tab
- Verify .env variables are correct
- Ensure FACEBOOK_SOURCES URLs are valid

---

## Docker Deployment

Run BY BOTS in Docker for consistent environments.

### Prerequisites

- Docker Desktop installed (docker.com/products/docker-desktop)
- Docker running and accessible
- .env file configured in project root

### Using Docker Compose

Easiest method - runs bot and optional dashboard:

```bash
docker compose -f config/docker-compose.yml up -d --build
```

To stop:
```bash
docker compose -f config/docker-compose.yml down
```

To view logs:
```bash
docker compose -f config/docker-compose.yml logs -f bybots
```

### With Dashboard Service

```bash
docker compose -f config/docker-compose.yml --profile dashboard up -d --build
```

Dashboard runs on http://127.0.0.1:5000

### Manual Docker Commands

Build image:
```bash
docker build -f config/Dockerfile -t by-bots .
```

Run container:
```bash
docker run -d --name by-bots-bot \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  by-bots
```

View logs:
```bash
docker logs -f by-bots-bot
```

Stop container:
```bash
docker stop by-bots-bot
docker rm by-bots-bot
```

### Data Persistence

Logs and database files are stored in volumes:
- logs/ directory mounted to /app/logs
- data/ directory mounted to /app/data

Delete these to reset database (posts will be rescanned).

---

## Windows Task Scheduler

Run bot automatically at Windows startup.

### Create Scheduled Task

1. Open Windows Task Scheduler
2. Click "Create Task" on right sidebar
3. Set Name: "BY BOTS Discord Bot"
4. Check "Run with highest privileges"

### Configure Trigger

1. Click "Triggers" tab
2. Click "New"
3. Select "At startup"
4. Click OK

### Configure Action

1. Click "Actions" tab
2. Click "New"
3. Set:
   - Program/script: python
   - Arguments: -c "import os; os.system('run.bat bot')"
   - Start in: C:\path\to\BY-BOTS
4. Click OK

### Test Task

1. Right-click task in list
2. Click "Run"
3. Check if bot comes online in Discord

### Enable/Disable

- Right-click task, select "Enable" or "Disable"
- Task runs automatically on next Windows restart

### Troubleshooting

Bot doesn't start:
- Check task history for error messages
- Verify Python path is correct
- Check .env file exists and has valid credentials

Note: Bot will stop when PC shuts down. For continuous 24/7 operation, use cloud hosting (Railway.app).

---

## Summary Table

| Deployment | Cost | 24/7 | Setup Time | Best For |
|-----------|------|------|-----------|----------|
| Local (PC) | Free | When PC on | 10 minutes | Development, testing |
| Task Scheduler | Free | When PC on | 15 minutes | Always-on home server |
| Docker | Free | When running | 15 minutes | Consistent environments |
| Railway.app | Free (with credits) | Yes | 10 minutes | Production, cloud-native |

---

## Support

For issues with specific deployments:

1. Check Troubleshooting section in main README.md
2. Review logs:
   - Local: logs/bybots.log
   - Railway: Console tab in dashboard
   - Docker: docker logs CONTAINER_NAME

3. Verify configuration:
   - All required environment variables set
   - Discord token and channel IDs are valid
   - Facebook URLs are accessible
