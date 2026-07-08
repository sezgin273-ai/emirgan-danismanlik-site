<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_localized_content();
$is_home = false;
$kvkk = $content['kvkk'];
$page_title = $kvkk['title'] . ' — ' . $content['site']['title'];
$page_description = $kvkk['intro'];
$canonical_path = '/kvkk.php';
$ui = $content['ui'];
$currentLang = current_site_lang();
?>
<!DOCTYPE html>
<html lang="<?= e($content['site']['lang']) ?>" dir="<?= e(site_html_dir($currentLang)) ?>">
<?php require __DIR__ . '/includes/head.php'; ?>
<body class="page-kvkk">
<?php require __DIR__ . '/includes/header.php'; ?>

<main id="main-content" class="kvkk-main">
    <div class="container">
        <article class="kvkk-article reveal" id="kvkk" aria-labelledby="kvkk-heading">
            <div class="section-header">
                <div class="gold-divider" aria-hidden="true"></div>
                <h1 id="kvkk-heading" class="section-title"><?= e($kvkk['title']) ?></h1>
            </div>
            <p class="kvkk-intro"><?= e($kvkk['intro']) ?></p>

            <?php foreach ($kvkk['sections'] as $section): ?>
                <section class="kvkk-section">
                    <h2><?= e($section['heading']) ?></h2>
                    <?php foreach ($section['paragraphs'] as $paragraph): ?>
                        <p><?= e($paragraph) ?></p>
                    <?php endforeach; ?>
                </section>
            <?php endforeach; ?>

            <p class="kvkk-back">
                <a class="btn btn-outline-navy" href="<?= e(site_lang_url('/')) ?>"><?= e($ui['back_home']) ?></a>
            </p>
        </article>
    </div>
</main>

<?php require __DIR__ . '/includes/footer.php'; ?>
</body>
</html>
