FROM node:22-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG API_ORIGIN=http://django:8000
ARG AI_ORIGIN=http://ai:8000
ENV API_ORIGIN=${API_ORIGIN}
ENV AI_ORIGIN=${AI_ORIGIN}
ENV NODE_ENV=production

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
