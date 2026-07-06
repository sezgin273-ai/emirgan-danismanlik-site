<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_content();
$is_home = false;
$kvkk = $content['kvkk'];
$page_title = $kvkk['title'] . ' — ' . $content['site']['title'];
$page_description = $kvkk['intro'];
$ui = $content['ui'];
?>
<!DOCTYPE html>
<html lang="<?= e($content['site']['lang']) ?>">
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

            <?php if (!empty($kvkk['note'])): ?>
                <p class="kvkk-note"><em><?= e($kvkk['note']) ?></em></p>
            <?php endif; ?>

            <p class="kvkk-back">
                <a class="btn btn-outline-navy" href="/"><?= e($ui['back_home']) ?></a>
            </p>
        </article>
    </div>
</main>

<?php require __DIR__ . '/includes/footer.php'; ?>
</body>
</html>
