<?php
declare(strict_types=1);

/** @var array $content */
/** @var string $page_title */
/** @var string|null $page_description */

$site = $content['site'];
$assets = $site['assets'];
$meta_description = $page_description ?? $content['hero']['description'];
?>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($page_title) ?></title>
    <meta name="description" content="<?= e($meta_description) ?>">
    <meta property="og:type" content="website">
    <meta property="og:title" content="<?= e($page_title) ?>">
    <meta property="og:description" content="<?= e($meta_description) ?>">
    <meta property="og:locale" content="tr_TR">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="<?= e($page_title) ?>">
    <meta name="twitter:description" content="<?= e($meta_description) ?>">
    <link rel="icon" href="<?= e($assets['favicon']) ?>" type="image/png">
    <link rel="apple-touch-icon" href="<?= e($assets['apple_touch_icon']) ?>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/css/tokens.css">
    <link rel="stylesheet" href="/assets/css/main.css">
</head>
