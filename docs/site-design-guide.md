# Site Design Guide

This guide captures the current visual system of the local coded version of `eventsurpriz.uz` as it exists in this repo on April 17, 2026. Use it as the default reference when creating new pages, sections, widgets, or UI states.

## Source Of Truth

Primary implementation sources:

- `content/routes/index/head.html`
- `content/routes/index/header.html`
- `content/routes/index/content.html`
- `content/routes/index/footer.html`
- `content/routes/prices/head.html`
- `content/routes/prices/content.html`
- `content/routes/contacts/head.html`
- `content/routes/contacts/content.html`
- `content/routes/catalog/head.html`
- `content/routes/catalog/content.html`
- `content/routes/character/labubu/head.html`
- `content/routes/character/labubu/content.html`
- `core/loader.py`

Important note:

- The raw route bundles come from the original WordPress markup.
- The final local presentation also depends on `core/loader.py`, which applies current project-wide visual overrides such as seasonal hiding, Instagram badge replacement, year replacement, and tab/carousel stabilization.

## Overall Visual Language

The brand style is not minimal, corporate, or neutral. It is festive, theatrical, child-event oriented, and deliberately bright.

Recurring qualities:

- large friendly typography
- bold color blocking instead of subtle gray UI
- rounded shapes almost everywhere
- mixed decorative backgrounds: confetti, brush waves, balloons, bunting, stars
- image-led cards with strong color overlays
- white or beige surfaces placed over vivid purple branding
- CTA buttons that look tactile and pill-shaped

When adding new UI, prefer expressive layouts over generic SaaS composition.

## Layout And Spacing

Stable layout rules seen across pages:

- main desktop container width is usually `1440px`
- some boxed sections use `1300px`
- pages are built from stacked full-width sections with boxed inner containers
- section gaps frequently use `20px`, `30px`, or `50px`
- major section padding tends to live in the `25px` to `50px` range
- hero sections are tall and visual, not cramped; home hero uses roughly `70vh`

Common rhythm:

- eyebrow / pretitle
- large main heading
- short supportive copy
- CTA row
- cards, grid, carousel, or form

## Typography

### Primary Families

- `Rubik`: base UI, body copy, nav, buttons, metadata, price lines, footer, forms
- `Balsamiq Sans`: major headings and emotionally warm titles
- `Amatic SC`: handwritten-style pretitle / section eyebrow
- `Montserrat Alternates`: card titles inside show-program cards
- `Roboto`: appears rarely, mostly as inherited or plugin-level supporting text

### Usage Pattern

- body and interface text: `Rubik`
- key headline: `Balsamiq Sans`
- smaller expressive lead-in above headline: `Amatic SC`
- promo/show card titles: `Montserrat Alternates`

### Typical Sizes

- nav: `18px`, medium weight
- base body: `16px`
- hero paragraph: `18px`
- contact icon-list text: `20px` desktop, smaller on mobile
- small meta text in cards: `13px` to `16px`
- header CTA text: `14px`
- section eyebrow: around `40px`
- hero eyebrow: `50px`
- major section title: `40px` to `60px`

### Weight Pattern

- body: `400`
- nav / secondary CTA / utility headings: `500`
- major labels and CTA text: `600` to `700`

## Color System

These are the core repeated colors in the current codebase.

### Brand Core

- Purple: `#6C1BE3`
- Orange: `#F26A20`
- Hot pink: `#F80D66`
- Warm yellow: `#FFCA24`
- Accent yellow variant: `#FEC02D`
- Beige section background: `#F6F3ED`

### Supporting Colors

- White: `#FFFFFF`
- Dark text: `#181818`
- Dark slate text: `#1E293B`
- Supporting text slate: `#334155`
- Light divider / muted footer text: `#E7E7E7`
- Dropdown border neutral: `#EEEEEE`

### Interactive / Hover

- bright blue hover for many CTA buttons: `#0088CC`
- darker blue used on product Telegram CTA hover: `#155372`
- warm orange hover for some sidebar/category links: `#FEC02D`

### Practical Mapping

- white background + dark text for header, tabs, and clean content areas
- purple background for brand anchors, footer, secondary CTAs
- orange for primary action or warm emphasis
- pink for energetic show-program section titles and card backplates
- yellow for icons, highlights, and ordering buttons on show cards
- beige for price/show section backdrop

## Shape Language

Rounded geometry is a constant across the site.

Common radii:

- `15px`: cards, images, map embed, product gallery corners
- `20px`: some footer form/button elements and mobile form container shapes
- `35px`: major CTA pill buttons
- `999px`: circular arrows, tag pills, some badges

Avoid sharp rectangles unless the original section already uses them.

## Core Components

## Header

Visual behavior:

- white sticky header
- logo on the left
- centered / left-centered nav
- phone number emphasized on the right
- orange uppercase CTA button
- mobile uses a slide-in popup menu

Implementation details pulled from current code:

- nav items: `Rubik`, `18px`, `500`, dark text, orange active/hover
- header CTA: orange fill, uppercase, `14px`, bold, `35px` radius
- CTA hover shifts to blue
- dropdown menu: white surface, `10px` radius, light border, orange active state

New pages should not introduce a different header style.

## Hero Sections

The home hero defines the site's tone:

- dark image-based background with overlay
- large yellow handwritten pretitle
- large white friendly headline
- white descriptive paragraph
- two strong pill CTAs
- brush-wave divider at the section edge

Home hero values:

- pretitle: `Amatic SC`, yellow
- main heading: `Balsamiq Sans`, white
- copy: `Rubik`, white
- dual CTA pattern:
  - purple pill
  - orange pill

When building a new landing-style page, this is the preferred opening pattern.

## Section Heading Pair

This is one of the strongest recurring motifs:

- first line: expressive `Amatic SC`, usually purple
- second line: large `Balsamiq Sans`, usually hot pink or orange

Examples:

- home show section
- prices page
- contacts page

Use this paired-heading formula before big content blocks.

## Buttons

### Main CTA Style

- pill radius: `35px`
- bold uppercase or near-uppercase text
- `Rubik`
- large horizontal padding
- icon allowed, usually trailing Telegram or arrow icon

### Known Button Variants

- orange fill, white text: main booking / action CTA
- purple fill, white text: secondary but still high-emphasis CTA
- yellow fill, black text: order button inside show cards
- blue fill: Telegram button on character detail
- transparent text-button: back link on product detail

### Hover Pattern

- orange and purple often hover to blue
- yellow often deepens to orange

Do not introduce thin-outline ghost buttons as the default visual language.

## Tabs And Carousels

The show-program UI is one of the key brand components.

Visual pattern:

- tabs sit on a light beige section background
- inactive tabs are white rounded capsules
- active tab is orange
- text is bold, dark, centered
- content usually shows 3 cards on desktop, fewer on smaller widths

Behavior notes:

- this area relies on nested Elementor carousels and tab widgets
- the local project has a stabilization script in `core/loader.py`
- any new tabbed/carousel section should preserve the same visual density and rounded white-tab pattern

## Show Program Cards

These are intentionally loud and festive.

Recurring structure:

- saturated colored background, often pink or themed image background
- semi-transparent top strip / inner banner
- title in `Montserrat Alternates`
- subhead and labels in `Rubik`
- white text on vivid background
- icon list with yellow minus icons
- price list below
- bright yellow "Заказать" button

Card traits:

- very rounded
- layered visuals
- strong contrast
- not minimalist

If creating a new service card, match this theatrical energy.

## Footer

The footer is a major branded zone, not an afterthought.

Structure:

- top contact form block
- brush-wave transition into a large purple brand footer
- phone, brand text, nav, and social block
- bottom legal row

Footer styling:

- dominant purple background
- white headings
- muted light text for description and links
- orange hover states
- repeated navigation
- social badge integrated as a visual object, not plain text link

Current local note:

- promo carousel is intentionally hidden by `core/loader.py`
- the Instagram badge is currently rendered via local custom HTML/CSS rather than the original image

## Forms

The footer form is the main form reference.

Traits:

- rounded inputs
- clear single-column stacking on mobile
- strong submit button
- uppercase submit label
- concise legal text below fields

Current footer form specifics:

- submit button uses white background and dark text by default
- hover shifts to purple with white text
- button radius is softer than the `35px` CTA pills

Use this form language instead of browser-default forms.

## Contacts Page

The contacts page is comparatively calm.

Pattern:

- breadcrumb first
- paired heading system
- icon-list contact details
- Instagram/social block
- CTA button
- rounded map embed

Styling:

- contact icons use orange
- primary texts remain `Rubik`
- heading uses purple eyebrow + orange `Balsamiq` title
- map uses `15px` corners

This is the default pattern for informational pages.

## Catalog And Category Pages

Catalog uses Astra/WooCommerce archive styling but still sits inside the same brand system.

Layout:

- left sidebar filter column
- right product grid
- strong use of white cards against colored sidebar blocks

Sidebar:

- widgets are dark purple blocks
- widget titles are white `Balsamiq Sans`
- category links are white with yellow hover
- tag cloud chips are rounded pills

Product cards:

- large portrait image
- title below image
- "Подробнее" CTA
- optional excerpt text
- grid layout, usually 3 columns desktop

When building list pages, reuse this two-column archive composition rather than inventing a new filter layout.

## Character Detail Pages

Character detail pages follow a stable commerce-like template:

- back link and breadcrumb at the top
- large product image left
- title and short description right
- phone CTA + Telegram CTA
- related characters grid below

Known styling:

- breadcrumb base text dark slate, links orange
- primary CTA orange uppercase pill
- Telegram CTA blue uppercase pill
- product gallery corners rounded
- related characters reuse catalog card style

Any new detail page for a service, hero, or package should stay close to this structure.

## Decorative Assets

The site uses decorative assets heavily and intentionally. Repeated motifs include:

- brush-wave SVG dividers
- confetti patterns
- balloons
- bunting / flag banners
- stars and sparkles
- character cutouts layered over colored backgrounds

Avoid flat empty backgrounds unless the original section is intentionally quiet. New sections should usually have at least one subtle branded decorative layer.

## Motion And Interaction

Observed motion patterns:

- sticky header reveal animation
- popup mobile menu
- Swiper carousel transitions
- hover color changes on buttons and links
- gentle button pulse on form submit

Interaction should feel lively but not over-animated. Prefer short reveal or hover feedback over complex animation choreography.

## Responsive Behavior

Important responsive habits already used across the site:

- custom breakpoints extend beyond the default trio
- tab rows can horizontally scroll on smaller devices
- carousels step from 3 to 2 to 1 cards
- button font size and padding shrink slightly on narrower screens
- footer collapses from row layout to stacked layout
- large decorative images disappear or reduce heavily on mobile

Do not build desktop-only sections. Mobile adaptation is part of the design language.

## Current Local Overrides

These are active today and must be remembered when extending the site:

- seasonal snow is disabled
- promo sections are hidden
- New Year links and show tabs are deprioritized
- homepage New Year showcase is hidden
- Instagram references point to `https://www.instagram.com/animator.surpriz/`
- the Instagram badge is a custom local component
- local tabs/carousels are stabilized by injected JS in `core/loader.py`

Any future feature touching these areas should respect the current override layer instead of reintroducing old live behavior by accident.

## Build Rules For New UI

When adding new pages or functionality, default to these rules:

- use `Rubik` for interface and body text
- use `Balsamiq Sans` for the main warm title
- use `Amatic SC` for the expressive pretitle when the section needs energy
- stay inside the purple / orange / pink / yellow / beige palette
- prefer rounded cards and pill buttons
- keep section composition image-led and festive
- reuse existing header, footer, tab, card, catalog, and CTA patterns before inventing new ones
- keep hover states warm and obvious
- preserve strong mobile behavior

Avoid these mistakes:

- neutral gray corporate styling
- square buttons or sharp cards
- flat white pages without decoration
- mixing in unrelated font stacks
- dark mode re-themes
- tiny typography
- thin low-contrast outlines as the main call to action

## Practical Default Template For A New Page

If a new page has no special requirements, build it in this order:

1. reuse the standard header
2. start with breadcrumb if it is an inner page
3. add an `Amatic SC` eyebrow
4. add a `Balsamiq Sans` headline
5. add `Rubik` support copy
6. add one or two pill CTAs
7. place the main content inside a `1440px` boxed section
8. use rounded cards or image blocks for the core content
9. finish with the standard footer

## Maintenance Note

If the design system changes later, update this file in the same commit as the UI change. Treat it as a living reference, not a one-time note.
