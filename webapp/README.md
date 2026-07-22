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

## Google Analytics

IndianKumbh.com uses Google Analytics 4 with this measurement ID:

```bash
NEXT_PUBLIC_GA_MEASUREMENT_ID=G-HW223XXYK2
```

If the environment variable is missing, the app falls back to `G-HW223XXYK2` so production tracking still works for the current site.

## Booking.com affiliate hotel redirects

IndianKumbh.com uses an internal redirect route for hotel affiliate links:

```text
/go/booking?city=ujjain&checkin=2026-07-15&checkout=2026-07-16&adults=2&rooms=1&campaign=ujjain-kumbh-2028
```

To enable Booking.com affiliate attribution after approval:

1. Apply for the Booking.com Affiliate Partner Programme.
2. Add the server-side affiliate ID to `.env`:

```bash
BOOKING_AFFILIATE_ID=your_booking_affiliate_id
```

`NEXT_PUBLIC_BOOKING_AFFILIATE_ID` should only be used if a future client-side widget requires it. Prefer `/go/booking` because it validates city/date inputs, logs a non-personal outbound click, and redirects safely.

To test locally:

```bash
npm run test:integration
npm run build
```

Then open:

```text
http://localhost:3000/go/booking?city=ujjain&checkin=2026-07-15&checkout=2026-07-16&adults=2&rooms=1&campaign=ujjain-kumbh-2028
```

Never use temporary Booking.com browser/session parameters such as `chal_t` or `force_referer`. The app should not pass personal data to Booking.com affiliate URLs.

## Unified travel redirects

Use `/go/travel` for bus, hotel, flight and train redirects. IndianKumbh validates input, builds a safe partner URL, logs a non-personal outbound click to `data/outbound-clicks.json`, and redirects the user to the partner site.

Examples:

```text
/go/travel?mode=bus&from=bengaluru&to=ujjain&date=2026-07-13&campaign=ujjain-kumbh-2028
/go/travel?mode=hotel&city=indore&checkin=2026-07-15&checkout=2026-07-16&adults=2&rooms=1&campaign=ujjain-kumbh-2028
/go/travel?mode=flight&from=bengaluru&to=indore&departureDate=2026-07-13&adults=2&campaign=ujjain-kumbh-2028
/go/travel?mode=train&from=mumbai&to=ujjain&date=2026-07-13&campaign=ujjain-kumbh-2028
```

Partner variables:

```bash
REDBUS_AFFILIATE_ID=
REDBUS_CAMPAIGN_PREFIX=indiankumbh
BOOKING_AFFILIATE_ID=
BOOKING_LABEL_PREFIX=indiankumbh
EASEMYTRIP_AFFILIATE_ID=
EASEMYTRIP_CAMPAIGN_PREFIX=indiankumbh
YATRA_AFFILIATE_ID=
YATRA_CAMPAIGN_PREFIX=indiankumbh
IRCTC_AFFILIATE_ID=
IRCTC_CAMPAIGN_PREFIX=indiankumbh
THRILLOPHILIA_PARTNER_ID=
LEAD_NOTIFICATION_EMAIL=admin@indiankumbh.com
```

RedBus city IDs are intentionally marked as `TODO_VERIFY...` in `src/data/travelCities.ts` until verified from partner documentation. The RedBus builder refuses to generate fake city-ID links.

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
- `NEXT_PUBLIC_GA_MEASUREMENT_ID` with the Google Analytics measurement ID if it changes
- contact form placeholders with a real endpoint

Content is static-first in focused JSON files under `data/`, ready to move into MDX or a CMS as editorial needs grow.

For Cloudflare, proxy the DNS record, use SSL mode `Full (strict)`, enable Brotli and leave versioned `/_next/static` assets cached.
