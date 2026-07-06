<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_content();
$site = $content['site'];
$hero = $content['hero'];
$intro = $content['intro'];
$about = $content['about'];
$vision = $content['vision'];
$mission = $content['mission'];
$team = $content['team'];
$services = $content['services'];
$contact = $content['contact'];
?>
<!DOCTYPE html>
<html lang="<?= e($site['lang']) ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= e($site['title']) ?></title>
    <link rel="stylesheet" href="/assets/css/tokens.css">
</head>
<body>
    <header>
        <h1><?= e($hero['company']) ?></h1>
        <p><?= e($hero['tagline']) ?></p>
    </header>

    <main>
        <section id="hero" aria-labelledby="hero-heading">
            <h2 id="hero-heading"><?= e($hero['company']) ?></h2>
            <p><strong><?= e($hero['tagline']) ?></strong></p>
            <p><?= e($hero['description']) ?></p>
        </section>

        <section id="intro" aria-labelledby="intro-heading">
            <h2 id="intro-heading"><?= e($intro['title']) ?></h2>
            <p><?= e($intro['text']) ?></p>
        </section>

        <section id="about" aria-labelledby="about-heading">
            <h2 id="about-heading"><?= e($about['title']) ?></h2>
            <h3><?= e($about['heading']) ?></h3>
            <?php foreach ($about['paragraphs'] as $paragraph): ?>
                <p><?= e($paragraph) ?></p>
            <?php endforeach; ?>
        </section>

        <section id="vision" aria-labelledby="vision-heading">
            <h2 id="vision-heading"><?= e($vision['title']) ?></h2>
            <p><?= e($vision['text']) ?></p>
        </section>

        <section id="mission" aria-labelledby="mission-heading">
            <h2 id="mission-heading"><?= e($mission['title']) ?></h2>
            <p><?= e($mission['text']) ?></p>
        </section>

        <section id="team" aria-labelledby="team-heading">
            <h2 id="team-heading"><?= e($team['title']) ?></h2>
            <p><?= e($team['intro']) ?></p>
            <ul>
                <?php foreach ($team['members'] as $member): ?>
                    <li>
                        <article>
                            <h3><?= e($member['name']) ?></h3>
                            <p><strong><?= e($member['title']) ?></strong></p>
                            <p><?= e($member['description']) ?></p>
                        </article>
                    </li>
                <?php endforeach; ?>
            </ul>
        </section>

        <section id="services" aria-labelledby="services-heading">
            <h2 id="services-heading"><?= e($services['title']) ?></h2>
            <ol>
                <?php foreach ($services['items'] as $service): ?>
                    <li>
                        <article>
                            <h3><?= e($service['title']) ?></h3>
                            <p><?= e($service['description']) ?></p>
                        </article>
                    </li>
                <?php endforeach; ?>
            </ol>
        </section>

        <section id="contact" aria-labelledby="contact-heading">
            <h2 id="contact-heading"><?= e($contact['title']) ?></h2>
            <h3><?= e($contact['heading']) ?></h3>
            <address>
                <?php foreach ($contact['addresses'] as $address): ?>
                    <p>
                        <strong><?= e($address['label']) ?>:</strong>
                        <?= e($address['text']) ?>
                    </p>
                <?php endforeach; ?>
                <p>
                    <strong>E-posta:</strong>
                    <a href="mailto:<?= e($contact['email']) ?>"><?= e($contact['email']) ?></a>
                </p>
            </address>
        </section>
    </main>

    <footer>
        <p>
            <a href="/kvkk.php">KVKK Aydınlatma Metni</a>
        </p>
        <p>&copy; <?= date('Y') ?> <?= e($site['title']) ?></p>
    </footer>
</body>
</html>
