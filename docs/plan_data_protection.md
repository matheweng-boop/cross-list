# Plan: data protection and review before publishing (owner, 26 Oct 2026)

Owner, verbatim: "we need to start implementing functions that are related to data protection. And everything that is
not publicly sourced needs to be reviewed first before going to the site." Agreed to build in the daily run of
26 Oct 2026 ("Data protection can run this evening"). All four decisions are settled (below); build on the run's branch.

## 1. Source label on all content
public (with link) · generated from public data · owner input · guest input (already reviewed before use).

## 2. Review gate: nothing non-public reaches the site unreviewed
- Pending review first: owner-entered prices, uploads (pictures, diagrams), free-text notes and edits shown on pages,
  research without a public source. Not shown on pages, in Shareable reports / PDF / PowerPoint, in scores or market
  figures until approved.
- Reviewed in Data management > To confirm (Approve / Reject, one tap, with the reason it was held).
- Shareable exports refuse to build while an unreviewed item would be included, naming the item.

## 2b. Every input is screened (owner, 26 Oct 2026)
Owner, verbatim: "Any input should be evaluated for pattern and potential insider information that needs to be
approved." Every input - the owner's own, guests', uploads, comments, prices, edits, and anything a run adds - is
screened before it shows. Flagged items are held for the owner's approval; unflagged public-sourced items pass.
Screen for:
- patterns: e-mail addresses, phone numbers, personal names with company context, "confidential", "internal",
  "NDA", "do not share", "preliminary", "roadmap", "under development", "not yet announced";
- potential insider information: unannounced products or part numbers not in any public catalogue or datasheet we
  hold, roadmaps and launch dates, internal codes or project names, manufacturing site / fab names
  (app/services/site_guard.py), customer programmes or design wins without a public source, prices or quotes,
  revenue, volume or forecast figures without a public source, internal e-mail domains or file paths;
- each flag says why ("part number not in any public source", "looks like a quote") and the owner approves, edits or
  rejects in To confirm.

## 3. Data-protection functions
- Checks on every text field and upload: e-mail addresses, phone numbers, "confidential" / "internal", public names already in the data, quote-like prices -> warning and hold for review. Strip image metadata (EXIF, GPS) on upload.
- Minimisation: pasted input is not stored unless the owner saves it (as Cross a list already works).
- Retention: feedback, comments and lookup requests deleted after a set time; daily inbox files (var/inbox) after a set
  time.
- Per person: export or delete everything a guest entered (GDPR).
- Privacy page: what is stored, why, how long, who can see it.
- Access log of owner pages, kept 90 days.

## Decisions to ask (suggested answers in brackets)
1. Settled (owner, 26 Oct 2026): every input, the owner's own included, is screened; flagged items wait for the owner's approval.
2. Settled (owner, 26 Oct 2026): retention 12 months for feedback, comments, lookup requests and inbox files.
3. ~~Customer-name list~~ Settled (owner, 26 Oct 2026): no customer names stored unless from public sources the site pulled itself; no private list.
4. Settled (owner, 26 Oct 2026): only the owner can approve data.
