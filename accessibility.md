---
type: "Reference"
title: "OKF ONS accessibility statement"
description: "Accessibility scope, status, known limitations and contact route for the public demonstrator."
resource: "https://chris-page-gov.github.io/okf-ons/accessibility.html"
tags: ["accessibility","wcag-2.2","public-service"]
generated: {"by":"process:okf-ons-bundle-builder","at":"2026-07-25T11:08:21Z"}
timestamp: "2026-07-25T11:08:21Z"
status: "draft"
sources: [{"id":"wcag-22","resource":"https://www.w3.org/TR/WCAG22/","title":"Web Content Accessibility Guidelines 2.2"},{"id":"uk-accessibility-regulations","resource":"https://www.legislation.gov.uk/uksi/2018/952/contents","title":"Public Sector Bodies Accessibility Regulations 2018"}]
---

# Accessibility statement

Last reviewed: 17 July 2026.

This statement covers the public `okf-ons` GitHub Pages demonstrator at
<https://chris-page-gov.github.io/okf-ons/>.

## Accessibility status

The demonstrator is designed toward the Web Content Accessibility Guidelines
(WCAG) 2.2 level AA and the UK public-sector accessibility requirements. It has
not yet received a formal independent accessibility audit and must not be
described as certified compliant.

## What should work

- Navigate every control with a keyboard.
- Use a visible skip link to reach dataset discovery.
- Read labelled search, facet, tab and comparison controls with assistive
  technology.
- Zoom and reflow the interface at narrow widths without losing functions.
- Use reduced-motion and increased-contrast operating-system preferences.
- Read a text table containing the same coordinates and geographic metadata as
  every visual extent diagram.
- Access every discovery and assurance artefact as an ordinary static JSON
  link.

The evidence tabs support Arrow Left, Arrow Right, Home and End as well as
normal Tab navigation. No modal keyboard traps are used.

## Known limitations

- The human result list is deliberately bounded. The complete machine-readable
  search index remains available through the OKF descriptor.
- Geographic coverage is currently represented by an extent diagram rather
  than an interactive map. Coordinates, CRS, geography code family, reference
  vintage and boundary variant are provided as the non-map alternative.
- Upstream descriptions can contain specialist statistical terminology that
  this demonstrator does not rewrite into plain language.
- Automated checks cannot establish every WCAG success criterion. Keyboard,
  screen-reader, 200% and 400% zoom, contrast and responsive-layout checks need
  continuing manual review.

## Technical approach

The site uses semantic HTML, native controls, explicit labels, visible focus,
status announcements and labels that do not depend on colour. The application
uses progressive enhancement: without JavaScript, direct links to the
descriptor, coverage, standards and evaluation JSON remain available.

The site does not use analytics, advertising, an external map service or
browser storage. It does not request an API key and stores no observations or
personal settings.

## Reporting a problem

Open an issue at <https://github.com/chris-page-gov/okf-ons/issues> and include:

- the page and task;
- browser and operating system;
- assistive technology, if applicable;
- expected and actual behaviour; and
- steps to reproduce.

Do not include personal information, confidential data or API credentials.

# Citations

- [Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/)
- [Public Sector Bodies Accessibility Regulations 2018](https://www.legislation.gov.uk/uksi/2018/952/contents)
