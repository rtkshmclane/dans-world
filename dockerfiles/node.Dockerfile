# Dockerfile template for Node.js/Express apps
# Copy this to your app's root directory as "Dockerfile"
# Adjust the port and entry script.

FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --production

COPY . .

# Change 3000 to your app's port
EXPOSE 3000

# Change "server.mjs" to your entry script
CMD ["node", "server.mjs"]
