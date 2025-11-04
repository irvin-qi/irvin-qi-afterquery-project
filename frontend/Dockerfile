FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies for the build step
RUN npm ci

# Copy application code
COPY . .

# Build the application
RUN npm run build

# Remove development dependencies for a leaner runtime image
RUN npm prune --omit=dev

EXPOSE 3000

CMD ["npm", "start"]