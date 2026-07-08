<?php
declare(strict_types=1);

/** @var array $content */
/** @var string $page_title */
/** @var string|null $page_description */
/** @var string|null $canonical_path */

$site = $content['site'];
$assets = $site['assets'];
$meta_description = $page_description ?? $content['site']['meta']['description'] ?? $content['hero']['description'];
$og_title = $content['site']['meta']['og_title'] ?? $page_title;
$og_description = $content['site']['meta']['og_description'] ?? $meta_description;
$site_url = rtrim((string) ($site['url'] ?? ''), '/');
$canonical_path = $canonical_path ?? '/';
$current_lang = current_site_lang();
$canonical_path_with_lang = site_lang_url($canonical_path, $current_lang);
$canonical_url = $site_url !== '' ? $site_url . $canonical_path_with_lang : $canonical_path_with_lang;
$og_image_path = (string) ($site['meta']['og_image'] ?? '');
$og_image_url = $og_image_path !== ''
    ? ($site_url !== '' && str_starts_with($og_image_path, '/') ? $site_url . $og_image_path : $og_image_path)
    : '';
$locale = site_og_locale($current_lang);
?>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($page_title) ?></title>
    <meta name="description" content="<?= e($meta_description) ?>">
    <link rel="canonical" href="<?= e($canonical_url) ?>">
    <meta name="theme-color" content="#10182C">
    <meta property="og:type" content="website">
    <meta property="og:url" content="<?= e($canonical_url) ?>">
    <meta property="og:title" content="<?= e($og_title) ?>">
    <meta property="og:description" content="<?= e($og_description) ?>">
    <meta property="og:locale" content="<?= e($locale) ?>">
    <?php foreach (SITE_LANGS as $langCode): ?>
    <?php $altUrl = $site_url . site_lang_url($canonical_path, $langCode); ?>
    <link rel="alternate" hreflang="<?= e($langCode) ?>" href="<?= e($altUrl) ?>">
    <?php endforeach; ?>
    <link rel="alternate" hreflang="x-default" href="<?= e($site_url . site_lang_url($canonical_path, 'tr')) ?>">
    <?php if ($og_image_url !== ''): ?>
    <meta property="og:image" content="<?= e($og_image_url) ?>">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <?php endif; ?>
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="<?= e($og_title) ?>">
    <meta name="twitter:description" content="<?= e($og_description) ?>">
    <?php if ($og_image_url !== ''): ?>
    <meta name="twitter:image" content="<?= e($og_image_url) ?>">
    <?php endif; ?>
    <link rel="icon" href="<?= e($assets['favicon']) ?>" type="image/png">
    <link rel="apple-touch-icon" href="<?= e($assets['apple_touch_icon']) ?>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/css/tokens.css">
    <link rel="stylesheet" href="/assets/css/main.css">
    <script src="/assets/js/main.js" defer onerror="document.documentElement.classList.remove('js')"></script>
</head>
