<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_content();
$is_home = true;
$page_title = $content['site']['title'];
$page_description = $content['site']['meta']['description'] ?? $content['hero']['description'];
$canonical_path = '/';

$hero = $content['hero'];
$intro = $content['intro'];
$about = $content['about'];
$vision = $content['vision'];
$mission = $content['mission'];
$team = $content['team'];
$services = $content['services'];
$process = $content['process'];
$contact = $content['contact'];
$ui = $content['ui'];
$assets = $content['site']['assets'];
?>
<!DOCTYPE html>
<html lang="<?= e($content['site']['lang']) ?>">
<?php require __DIR__ . '/includes/head.php'; ?>
<body class="page-home">
<?php require __DIR__ . '/includes/header.php'; ?>

<main id="main-content">
    <?php if (section_visible($content, 'hero')): ?>
    <section class="hero section-dark" id="hero" aria-labelledby="hero-heading">
        <div class="hero-watermark" aria-hidden="true" style="background-image: url('<?= e($assets['emblem']) ?>')"></div>
        <div class="container hero-grid">
            <div class="hero-content reveal">
                <p class="hero-eyebrow"><?= e($hero['company']) ?></p>
                <div class="hero-title-wrap">
                    <span class="hero-title-line hero-title-line--left" aria-hidden="true"></span>
                    <h1 id="hero-heading" class="hero-title">
                        <span class="hero-title-accent"><?= e($hero['tagline']) ?></span>
                    </h1>
                    <span class="hero-title-line hero-title-line--right" aria-hidden="true"></span>
                </div>
                <p class="hero-description"><?= e($hero['description']) ?></p>
                <div class="hero-actions">
                    <a class="btn btn-gold" href="#contact"><?= e($contact['heading']) ?></a>
                    <a class="btn btn-outline-light" href="#services"><?= e($services['title']) ?></a>
                </div>
            </div>

            <div class="hero-visual reveal" aria-label="<?= e($ui['hero_visual_label']) ?>">
                <div class="hero-visual-card">
                    <div class="hero-medallion" aria-hidden="true">
                        <span class="hero-medallion-ring hero-medallion-ring--outer"></span>
                        <span class="hero-medallion-ring hero-medallion-ring--inner"></span>
                        <img src="<?= e($assets['emblem']) ?>" alt="" class="hero-emblem">
                    </div>
                    <div class="hero-stats">
                        <div class="hero-stat">
                            <span class="hero-stat-value"><?= count($services['items']) ?></span>
                            <span class="hero-stat-label"><?= e($services['title']) ?></span>
                        </div>
                        <div class="hero-stat">
                            <span class="hero-stat-value"><?= count($team['members']) ?></span>
                            <span class="hero-stat-label"><?= e($team['title']) ?></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>
    <?php endif; ?>

    <?php if (section_visible($content, 'intro')): ?>
    <section class="intro section-light" id="intro" aria-labelledby="intro-heading">
        <div class="container">
            <div class="section-header reveal">
                <div class="gold-divider" aria-hidden="true"></div>
                <h2 id="intro-heading" class="section-title"><?= e($intro['title']) ?></h2>
            </div>
            <p class="intro-text reveal"><?= e($intro['text']) ?></p>
            <ul class="badge-list reveal" aria-label="<?= e($intro['title']) ?>">
                <?php foreach ($intro['badges'] as $badge): ?>
                    <li class="badge-item">
                        <span class="badge-icon"><?= badge_icon($badge['icon']) ?></span>
                        <span><?= e($badge['label']) ?></span>
                    </li>
                <?php endforeach; ?>
            </ul>
        </div>
    </section>
    <?php endif; ?>

    <?php if (section_visible($content, 'services')): ?>
    <section class="services section-cream" id="services" aria-labelledby="services-heading">
        <div class="container">
            <div class="section-header reveal">
                <div class="gold-divider" aria-hidden="true"></div>
                <h2 id="services-heading" class="section-title"><?= e($services['title']) ?></h2>
            </div>
            <div class="services-grid">
                <?php foreach ($services['items'] as $index => $service): ?>
                    <article class="service-card reveal" style="--reveal-delay: <?= $index * 80 ?>ms">
                        <div class="service-icon"><?= service_icon($service['icon']) ?></div>
                        <h3 class="service-title"><?= e($service['title']) ?></h3>
                        <p class="service-description"><?= e($service['description']) ?></p>
                    </article>
                <?php endforeach; ?>
            </div>
        </div>
    </section>
    <?php endif; ?>

    <?php if (section_visible($content, 'about')): ?>
    <section class="about section-light" id="about" aria-labelledby="about-heading">
        <div class="container">
            <div class="about-grid">
                <div class="about-text reveal">
                    <div class="gold-divider" aria-hidden="true"></div>
                    <h2 id="about-heading" class="section-title"><?= e($about['title']) ?></h2>
                    <h3 class="about-heading"><?= e($about['heading']) ?></h3>
                    <?php foreach ($about['paragraphs'] as $paragraph): ?>
                        <p><?= e($paragraph) ?></p>
                    <?php endforeach; ?>
                </div>
                <div class="about-cards reveal">
                    <article class="vision-mission-card">
                        <h3><?= e($vision['title']) ?></h3>
                        <p><?= e($vision['text']) ?></p>
                    </article>
                    <article class="vision-mission-card">
                        <h3><?= e($mission['title']) ?></h3>
                        <p><?= e($mission['text']) ?></p>
                    </article>
                </div>
            </div>
        </div>
    </section>
    <?php endif; ?>

    <section class="process section-dark" id="process" aria-labelledby="process-heading">
        <div class="container">
            <div class="section-header section-header--dark reveal">
                <div class="gold-divider" aria-hidden="true"></div>
                <h2 id="process-heading" class="section-title section-title--light"><?= e($process['title']) ?></h2>
            </div>
            <ol class="process-steps">
                <?php foreach ($process['steps'] as $index => $step): ?>
                    <li class="process-step reveal" style="--reveal-delay: <?= $index * 100 ?>ms">
                        <span class="process-step-number" aria-hidden="true"><?= $index + 1 ?></span>
                        <div class="process-step-body">
                            <h3 class="process-step-title"><?= e($step['title']) ?></h3>
                            <p class="process-step-description"><?= e($step['description']) ?></p>
                        </div>
                    </li>
                <?php endforeach; ?>
            </ol>
        </div>
    </section>

    <?php if (section_visible($content, 'team')): ?>
    <section class="team section-light" id="team" aria-labelledby="team-heading">
        <div class="container">
            <div class="section-header reveal">
                <div class="gold-divider" aria-hidden="true"></div>
                <h2 id="team-heading" class="section-title"><?= e($team['title']) ?></h2>
                <p class="section-subtitle"><?= e($team['intro']) ?></p>
            </div>
            <div class="team-grid">
                <?php foreach ($team['members'] as $index => $member): ?>
                    <article class="team-card reveal" style="--reveal-delay: <?= $index * 80 ?>ms">
                        <div class="team-avatar" aria-hidden="true">
                            <?php if (!empty($member['photo'])): ?>
                                <img src="<?= e($member['photo']) ?>" alt="" class="team-photo">
                            <?php else: ?>
                                <span class="team-monogram"><?= e(initials($member['name'])) ?></span>
                            <?php endif; ?>
                        </div>
                        <h3 class="team-name"><?= e($member['name']) ?></h3>
                        <p class="team-title"><?= e($member['title']) ?></p>
                        <p class="team-description"><?= e($member['description']) ?></p>
                    </article>
                <?php endforeach; ?>
            </div>
        </div>
    </section>
    <?php endif; ?>

    <?php if (section_visible($content, 'contact')): ?>
    <section class="contact section-cream" id="contact" aria-labelledby="contact-heading">
        <div class="container">
            <div class="contact-intro reveal">
                <div class="gold-divider" aria-hidden="true"></div>
                <h2 id="contact-heading" class="section-title"><?= e($contact['title']) ?></h2>
                <p class="section-subtitle"><?= e($contact['heading']) ?></p>
            </div>
            <div class="contact-grid">
                <form class="contact-form reveal" id="contact-form" action="/api/contact.php" method="post" novalidate data-success="<?= e($contact['form']['success']) ?>" data-error="<?= e($contact['form']['error']) ?>">
                    <div class="form-row visually-hidden" aria-hidden="true">
                        <label for="contact-website">Website</label>
                        <input type="text" id="contact-website" name="website" tabindex="-1" autocomplete="off">
                    </div>
                    <div class="form-row">
                        <label for="contact-name"><?= e($contact['form']['name']['label']) ?></label>
                        <input
                            type="text"
                            id="contact-name"
                            name="name"
                            required
                            autocomplete="name"
                            placeholder="<?= e($contact['form']['name']['placeholder']) ?>"
                        >
                    </div>
                    <div class="form-row">
                        <label for="contact-email"><?= e($contact['form']['email']['label']) ?></label>
                        <input
                            type="email"
                            id="contact-email"
                            name="email"
                            required
                            autocomplete="email"
                            placeholder="<?= e($contact['form']['email']['placeholder']) ?>"
                        >
                    </div>
                    <div class="form-row">
                        <label for="contact-phone"><?= e($contact['form']['phone']['label']) ?></label>
                        <input
                            type="tel"
                            id="contact-phone"
                            name="phone"
                            autocomplete="tel"
                            placeholder="<?= e($contact['form']['phone']['placeholder']) ?>"
                        >
                    </div>
                    <div class="form-row">
                        <label for="contact-subject"><?= e($contact['form']['subject']['label']) ?></label>
                        <input
                            type="text"
                            id="contact-subject"
                            name="subject"
                            required
                            placeholder="<?= e($contact['form']['subject']['placeholder']) ?>"
                        >
                    </div>
                    <div class="form-row">
                        <label for="contact-message"><?= e($contact['form']['message']['label']) ?></label>
                        <textarea
                            id="contact-message"
                            name="message"
                            rows="5"
                            required
                            placeholder="<?= e($contact['form']['message']['placeholder']) ?>"
                        ></textarea>
                    </div>
                    <p class="form-feedback" id="form-feedback" role="status" aria-live="polite" hidden></p>
                    <button type="submit" class="btn btn-navy"><?= e($contact['form']['submit']) ?></button>
                </form>

                <div class="contact-info reveal">
                    <?php foreach ($contact['addresses'] as $address): ?>
                        <article class="address-card">
                            <h3><?= e($address['label']) ?></h3>
                            <address><?= e($address['text']) ?></address>
                        </article>
                    <?php endforeach; ?>
                    <article class="address-card">
                        <h3><?= e($ui['email_label']) ?></h3>
                        <p>
                            <a href="mailto:<?= e($contact['email']) ?>"><?= e($contact['email']) ?></a>
                        </p>
                    </article>
                </div>
            </div>
        </div>
    </section>
    <?php endif; ?>
</main>

<?php require __DIR__ . '/includes/footer.php'; ?>
</body>
</html>
