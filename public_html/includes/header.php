<?php
declare(strict_types=1);

/** @var array $content */
/** @var bool $is_home */

$site = $content['site'];
$nav = $content['navigation'];
$ui = $content['ui'];
$assets = $site['assets'];
$home_href = $is_home ? '#hero' : site_lang_url('/#hero');
$currentLang = current_site_lang();
$langLabels = ['tr' => 'TR', 'en' => 'EN', 'de' => 'DE', 'ru' => 'RU', 'fa' => 'FA'];
?>
<a class="skip-link" href="#main-content"><?= e($ui['skip_to_content']) ?></a>

<header class="site-header" id="site-header">
    <div class="container header-inner">
        <a class="brand" href="<?= e($home_href) ?>" aria-label="<?= e($site['title']) ?>">
            <img src="<?= e($assets['logo_light']) ?>" alt="<?= e($site['title']) ?>" class="brand-logo <?= e(display_size_class($content, 'header_logo')) ?>">
        </a>

        <button
            class="nav-toggle"
            type="button"
            aria-expanded="false"
            aria-controls="site-nav"
            data-nav-toggle
            data-close-label="<?= e($ui['menu_close']) ?>"
        >
            <span class="nav-toggle-icon" aria-hidden="true"></span>
            <span class="visually-hidden" data-nav-toggle-label><?= e($ui['menu_open']) ?></span>
        </button>

        <nav class="site-nav" id="site-nav" aria-label="<?= e($site['title']) ?>">
            <ul class="nav-list">
                <?php foreach ($nav['items'] as $item): ?>
                    <?php if (!section_visible($content, $item['id'])) continue; ?>
                    <li>
                        <a
                            class="nav-link"
                            href="<?= $is_home ? e((string) $item['href']) : e(site_lang_url('/' . ltrim((string) $item['href'], '/'))) ?>"
                            data-nav-link="<?= e($item['id']) ?>"
                        ><?= e($item['label']) ?></a>
                    </li>
                <?php endforeach; ?>
            </ul>
            <a class="btn btn-gold btn-sm nav-cta" href="<?= $is_home ? e((string) $nav['cta']['href']) : e(site_lang_url('/' . ltrim((string) $nav['cta']['href'], '/'))) ?>">
                <?= e($nav['cta']['label']) ?>
            </a>
            <div class="lang-switcher" role="navigation" aria-label="Language selector">
                <?php foreach ($langLabels as $langCode => $langLabel): ?>
                    <?php $isActive = $currentLang === $langCode; ?>
                    <a
                        class="lang-link<?= $isActive ? ' is-active' : '' ?>"
                        href="<?= e('/?lang=' . $langCode . '#hero') ?>"
                        hreflang="<?= e($langCode) ?>"
                        lang="<?= e($langCode) ?>"
                        <?= $isActive ? 'aria-current="page"' : '' ?>
                    ><?= e($langLabel) ?></a>
                <?php endforeach; ?>
            </div>
        </nav>
    </div>
</header>
