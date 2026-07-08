<?php
declare(strict_types=1);

/** @var array $content */
/** @var bool $is_home */

$site = $content['site'];
$nav = $content['navigation'];
$ui = $content['ui'];
$kvkk = $content['kvkk'];
$assets = $site['assets'];
?>
<footer class="site-footer">
    <div class="container footer-grid">
        <div class="footer-brand">
            <img src="<?= e($assets['logo_dark']) ?>" alt="<?= e($site['title']) ?>" class="footer-logo <?= e(display_size_class($content, 'footer_logo')) ?>">
            <p class="footer-tagline"><?= e($content['hero']['tagline']) ?></p>
        </div>

        <div class="footer-links">
            <h2 class="footer-heading"><?= e($content['footer']['quick_links_title']) ?></h2>
            <ul>
                <?php foreach ($nav['items'] as $item): ?>
                    <?php if (!section_visible($content, $item['id'])) continue; ?>
                    <li>
                        <a href="<?= $is_home ? e((string) $item['href']) : e(site_lang_url('/' . ltrim((string) $item['href'], '/'))) ?>">
                            <?= e($item['label']) ?>
                        </a>
                    </li>
                <?php endforeach; ?>
                <li>
                    <a href="<?= e(site_lang_url('/kvkk.php')) ?>"><?= e($kvkk['title']) ?></a>
                </li>
            </ul>
        </div>

        <div class="footer-contact">
            <p>
                <a href="mailto:<?= e($content['contact']['email']) ?>">
                    <?= e($content['contact']['email']) ?>
                </a>
            </p>
        </div>
    </div>

    <div class="footer-bottom">
        <div class="container">
            <p>&copy; <?= date('Y') ?> <?= e($site['title']) ?></p>
        </div>
    </div>
</footer>