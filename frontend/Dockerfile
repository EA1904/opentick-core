FROM node:20-alpine

WORKDIR /app

# Copy package configuration
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy application source code
COPY . .

# Expose port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev"]
