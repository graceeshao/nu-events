# Inactive Instagram Accounts

Student org Instagram accounts that have been automatically marked inactive by the scraper (no posts in 1+ year). These accounts are skipped during scraping to save rate limit budget.

Last updated: 2026-03-29

| Organization | Handle | Last Post |
|---|---|---|
| Art Union | @artunion_nu | 2023-09-28 |
| Alexander Hamilton Society | @ahsnorthwestern | 2024-11-19 |
| Ahana Dance Project | @ahana_danceproject | 2025-02-21 |

## Notes

- Accounts are auto-detected as inactive when their most recent post is older than 365 days.
- The scraper checks activity during each batch and updates the database accordingly.
- If an org becomes active again, manually set `instagram_active = 1` in the database:
  ```sql
  UPDATE organizations SET instagram_active = 1 WHERE instagram_handle = 'handle_here';
  ```
- If an org's handle has changed, update it:
  ```sql
  UPDATE organizations SET instagram_handle = 'new_handle', instagram_active = 1, instagram_last_post_at = NULL WHERE name = 'Org Name';
  ```

This list will grow as the scraper cycles through all 427 orgs over the coming days.
