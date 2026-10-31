# Market Session Calendar

## Purpose
Provide a small, configurable exchange-session calendar. This layer handles
local trading sessions, weekly schedules, explicit holidays and special-day
overrides. It does not fetch exchange circulars or maintain an official holiday
feed.

## NSE baseline
The helper `nse_equity_derivatives_baseline` supplies a regular weekday
baseline of 09:15–15:30 in `Asia/Kolkata`. This is a configurable starting
schedule, not a verified calendar for a particular contract or date. The caller
must supply the applicable official holiday dates and special sessions before
using it for historical gap classification or trading decisions.

## Rules
- Sessions use local exchange wall-clock time.
- Opening time is inclusive; closing time is exclusive.
- Weekday numbering follows Python: Monday=0 through Sunday=6.
- A holiday closes the full date.
- A special-session entry replaces the weekly schedule for that date; an empty
  tuple means closed.
- Multiple sessions per day are supported, sorted and non-overlapping.
- Input timestamps must be timezone-aware and are converted to the calendar's
  timezone for evaluation.

## Not included
No automatic holiday downloads, exchange API, contract-specific calendars,
pre-open/closing auction logic, crypto 24/7 calendar, broker, strategy or order
execution. Do not treat the baseline as an official holiday list.
