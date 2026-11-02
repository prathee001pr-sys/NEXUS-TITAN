# NEXUS TITAN — Indian Market Data Vendor Due Diligence
**Research date:** 01 November 2026  
**Target:** 15-year 1-minute historical data for NIFTY / BANKNIFTY spot indices, expiry-specific futures and options; later controlled ₹50,000 virtual shadow validation.  
**Status:** Initial public-document review only. No vendor selected, no quote requested, no data purchased, and no licence approved.

## Executive decision

Do not buy a generic retail charting subscription for the project. NEXUS TITAN needs written rights for its intended use (local research, backtesting, paper/shadow simulation, retention in a local database, and encrypted external-SSD portability) plus confirmed historical depth per segment and contract type.

The most promising next enquiry is **AccelPix API / bulk historical delivery**, with **NSE Data & Analytics** as the authoritative direct-source enquiry. Global Datafeeds' published rolling intraday backfill is too short for the 15-year 1-minute requirement. TrueData is not acceptable for the planned paper/shadow workflow under its currently published terms unless the relevant exchange/vendor provides written permission that changes that position.

## Publicly documented findings

### 1. NSE Data & Analytics — authoritative direct enquiry

NSE Data & Analytics lists EOD/historical data products for Capital Market and F&O. Its domestic tariff effective 01 April 2026 lists **Historical Trade Data** at ₹1,10,000 per annum per site for Capital Market and separately ₹1,10,000 per annum per site for F&O. It lists **Historical Order & Trade Data** at ₹12,50,000 per annum per single site for Capital Market and separately ₹12,50,000 for F&O. Fees are exclusive of applicable taxes; the tariff table does not, by itself, establish that the Historical Trade Data product is the requested 1-minute OHLCV archive or that it covers 15 years contract-by-contract. That product specification must be confirmed before treating the price as applicable.

NSE's data-use policy says subscribers must state intended use and execute the relevant agreement. It also says offline modes such as CDs, hard drives and USB/removable storage are not permitted without prior approval. Therefore, carrying licensed data on TITAN's encrypted external SSD requires written approval; encryption does not replace the exchange's storage permission.

**Next enquiry:** request exact 1-minute historical product coverage by symbol/segment/expiry, 15-year start dates, options contractwise availability, format, cost, retention, permitted local storage, and internal research/backtest/shadow-use rights.

Official links:
- https://www.nse.in/static/nse-data-and-analytics/data-information-vending
- https://www.nseindia.com/static/nse-data-and-analytics/contact-us
- https://www.nseindia.com/static/market-data/nse-data-policy
- Domestic tariff PDF (effective 01-Apr-2026): https://nsearchives.nseindia.com//web/mediaattachment/2026-04/Download_Pricing_file_-_Domestic_clients_20260424122229.pdf

### 2. AccelPix — promising API / bulk-history enquiry; depth still unconfirmed

AccelPix publicly documents historical one-minute bars, contract and continuous series, REST/Python/Node API access, and an option-Greeks history service. Its API access is provisioned based on intended use and entitlements; it says years of tick and adjusted EOD history exist, while the amount of history covered by a specific entitlement depends on the project. Bulk historical delivery is separately available. API pricing is quoted based on symbol count, history depth, live versus historical access and licence class.

The public material does **not** give a definitive 15-year 1-minute coverage matrix for NIFTY/BANKNIFTY options contracts. The separate Pix Connect IEOD instructions state that the ordinary one-minute downloadable history for a subscriber begins from the realtime subscription start date; previous months/years require a separate enquiry. This reinforces the need for a written bulk-history quote instead of assuming a normal subscription includes deep backfill.

**Status:** Best vendor to ask first for a pilot quote, but not approved until it confirms exact years and paper/shadow/local-storage rights in writing.

Official links:
- https://accelpix.com/products/pix-api/
- https://support.accelpix.com/portal/en/kb/articles/pix-apis-realtime-and-historical-data-in-python
- https://support.accelpix.com/portal/en/kb/articles/how-to-download-daily-ieod-incremental-data-using-pix-connect

### 3. Global Datafeeds — useful API, but published intraday backfill is not enough

Global Datafeeds publishes historical Tick/Minute/Day/Week/Month APIs. Its published NFO table says 1/2/3/4-minute history has 3 calendar months of backfill; 5/6/10/12-minute history has 4.5 months; 15/20/30-minute history has 6 months. Its NFO futures continuous daily/weekly/monthly data is listed since 2010, but contractwise futures daily/weekly/monthly is listed as 3 calendar months and contractwise options daily/weekly/monthly as 1 calendar month. It does not publicly document 15 years of 1-minute NFO/options history on that page.

**Status:** Do not use as the sole 15-year 1-minute source on the currently published specification. Ask whether custom archival/bulk delivery is separately available, but do not assume it is.

Official link:
- https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/introduction/type-of-data-available/

### 4. TrueData — not approved for TITAN's paper/shadow phase under current published terms

TrueData advertises API access for NSE indices, futures and options, historical data, WebSocket/REST interfaces and 1-minute/tick backfill features. However, its published API terms state that it does not provide market data for virtual trading, paper trading, trading simulators, mock trading, or model portfolios. It also limits ordinary use to the single subscriber's own personal/proprietary use and requires separate exchange approval/licensing for redistribution or broader commercial use.

**Status:** Exclude from the ₹50,000 virtual shadow data path unless the vendor and exchange provide explicit written permission for the exact use case. Its displayed Velocity starting price is not an API price or proof of historical archive depth.

Official links:
- https://www.truedata.in/products/marketdataapi
- https://www.truedata.in/market-data-apis

## Required vendor questionnaire (must be answered in writing)

1. Exact first available date and last available date for NIFTY and BANKNIFTY spot/index 1-minute OHLCV.
2. Exact first/last dates for each NIFTY/BANKNIFTY futures expiry, contractwise, with volume and open interest.
3. Exact first/last dates for NIFTY/BANKNIFTY options by expiry, strike and CE/PE, contractwise, with volume/OI; clarify whether only EOD or true 1-minute bars are available.
4. Whether bid/ask, L1 depth, trades/ticks, timestamps, exchange sequence IDs and quote conditions are available; specify what is absent.
5. Raw versus adjusted series: corporate actions, futures roll methodology, expiry/roll handling, OI adjustments, index volume construction, and whether original raw files can also be delivered.
6. Missing-bar/correction policy, historical reprints, backfill guarantees, data-quality SLAs and sample files for selected dates.
7. Written permission for local backtest, internal research, ₹50,000 paper/shadow simulation, local SQLite/CSV storage, backups, and encrypted external-SSD portability.
8. Whether data may be used only by one individual/device, and any device, IP, concurrency, retention, or offline-access restrictions.
9. All-in cost: one-time bulk fee, recurring API subscription, per-segment/per-symbol charges, exchange/user fees, taxes, support, and renewal terms.
10. Licence document / agreement ID that can be stored in each NEXUS TITAN dataset manifest.

## Acceptance test before payment or integration

Obtain a small sample across distinct market regimes and contract expiries. Verify the actual file against the vendor's symbol master, expected session calendar, expiry/lot/tick metadata, complete date coverage, duplicate/missing/out-of-session candles, raw/adjusted rules, volume/OI consistency and SHA-256. Compare randomly selected bars and trade/quote records against an independent source or official records where available. Do not connect any feed to order execution. Only after legal use and data integrity are confirmed should the adapter be connected to historical research.

## Sources and review notes

This is a public-web review, not legal advice and not a guarantee of vendor inventory. Vendor claims are not treated as proof of exchange entitlement. All requirements should be included in the written order form/contract and verified against the exact purchased product.
