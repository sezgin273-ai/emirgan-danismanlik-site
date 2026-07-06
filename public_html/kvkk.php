<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_content();
$site = $content['site'];
$kvkk = $content['kvkk'];
?>
<!DOCTYPE html>
<html lang="<?= e($site['lang']) ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($kvkk['title']) ?> — <?= e($site['title']) ?></title>
    <link rel="stylesheet" href="/assets/css/tokens.css">
</head>
<body>
    <header>
        <h1><?= e($site['title']) ?></h1>
        <nav>
            <a href="/">Ana Sayfa</a>
        </nav>
    </header>

    <main>
        <article id="kvkk" aria-labelledby="kvkk-heading">
            <h2 id="kvkk-heading"><?= e($kvkk['title']) ?></h2>
            <p><?= e($kvkk['intro']) ?></p>

            <?php foreach ($kvkk['sections'] as $section): ?>
                <section>
                    <h3><?= e($section['heading']) ?></h3>
                    <?php foreach ($section['paragraphs'] as $paragraph): ?>
                        <p><?= e($paragraph) ?></p>
                    <?php endforeach; ?>
                </section>
            <?php endforeach; ?>

            <?php if (!empty($kvkk['note'])): ?>
                <p><em><?= e($kvkk['note']) ?></em></p>
            <?php endif; ?>
        </article>
    </main>

    <footer>
        <p><a href="/">Ana Sayfa</a></p>
        <p>&copy; <?= date('Y') ?> <?= e($site['title']) ?></p>
    </footer>
</body>
</html>
