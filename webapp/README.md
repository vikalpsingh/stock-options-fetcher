# Ujjain Kumbh Mela 2028 Travel Guide

Production-ready, mobile-first Next.js 15 travel planning website for Ujjain Kumbh Mela 2028 and Mahakal visitors.

## Architecture

- App Router with statically generated pages
- TypeScript + Tailwind CSS
- shadcn/ui-compatible primitives in `components/ui`
- Framer Motion progressive animations
- JSON editorial content in `data/`
- English/Hindi-ready locale structure in `app/[locale]` and `data/locales`
- FAQ and TravelGuide structured data
- Google Maps, WhatsApp sharing and printable itineraries

## Local development

```bash
npm install
npm run dev
```

The site runs at `http://localhost:3000`.

## Python Risk Tests

```bash
python -m pytest tests -v
```

The risk tests use mock data only and do not call Kite or the internet.

## Production (Ubuntu + PM2 + Nginx)

```bash
npm ci
npm run build
pm2 start ecosystem.config.cjs
pm2 save
```

Use `deploy/nginx.conf.example` as the Nginx starting point, add SSL with Certbot, and replace:

- `https://ujjain2028.in` with the final domain
- `G-XXXXXXXXXX` with the Google Analytics measurement ID
- contact form placeholders with a real endpoint

Content is static-first in focused JSON files under `data/`, ready to move into MDX or a CMS as editorial needs grow.

For Cloudflare, proxy the DNS record, use SSL mode `Full (strict)`, enable Brotli and leave versioned `/_next/static` assets cached.
