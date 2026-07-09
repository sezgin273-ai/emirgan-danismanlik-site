<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/bootstrap.php';

$content = load_localized_content();
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
$process = $content['process'] ?? ['title' => '', 'steps' => []];
$contact = $content['contact'];
$ui = $content['ui'];
$assets = $content['site']['assets'];
$currentLang = current_site_lang();

/** @return list<array{label:string,value:string}> */
function index_contact_hours_rows(array $contactBlock): array
{
    if (!isset($contactBlock['hours']) || !is_array($contactBlock['hours'])) {
        return [];
    }
    $title = trim((string) ($contactBlock['hours']['title'] ?? ''));
    if ($title === '') {
        return [];
    }
    $rows = $contactBlock['hours']['rows'] ?? [];
    if (!is_array($rows) || count($rows) === 0) {
        return [];
    }
    $valid = [];
    foreach ($rows as $row) {
        if (!is_array($row)) {
            continue;
        }
        $label = trim((string) ($row['label'] ?? ''));
        $value = trim((string) ($row['value'] ?? ''));
        if ($label === '' || $value === '') {
            continue;
        }
        $valid[] = ['label' => $label, 'value' => $value];
    }

    return $valid;
}

$contactHoursRows = index_contact_hours_rows($contact);
$contactHoursTitle = $contactHoursRows !== [] ? trim((string) ($contact['hours']['title'] ?? '')) : '';
?>
<!DOCTYPE html>
<html lang="<?= e($content['site']['lang']) ?>" dir="<?= e(site_html_dir($currentLang)) ?>">
<?php require __DIR__ . '/includes/head.php'; ?>
<body class="page-home <?= e(display_body_classes($content)) ?>">
<?php require __DIR__ . '/includes/header.php'; ?>

<main id="main-content">
    <?php if (section_visible($content, 'hero')): ?>
    <section class="hero section-dark" id="hero" aria-labelledby="hero-heading">
        <div class="hero-photo" aria-hidden="true">
            <picture>
                <source
                    type="image/webp"
                    srcset="/assets/img/hero-768.webp 768w, /assets/img/hero-1280.webp 1280w, /assets/img/hero-1920.webp 1920w"
                    sizes="100vw"
                >
                <img
                    src="/assets/img/hero-1280.jpg"
                    alt=""
                    width="1280"
                    height="716"
                    fetchpriority="high"
                    decoding="sync"
                >
            </picture>
        </div>
        <div class="hero-overlay" aria-hidden="true"></div>
        <?php if (hero_watermark_enabled($content)): ?>
        <div class="hero-watermark" aria-hidden="true" style="background-image: url('<?= e($assets['emblem']) ?>')"></div>
        <?php endif; ?>
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
                    <div class="hero-medallion <?= e(display_size_class($content, 'hero_emblem')) ?>" aria-hidden="true">
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
                        <div class="service-icon <?= e(display_size_class($content, 'service_icon')) ?>"><?= service_icon($service['icon']) ?></div>
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

    <?php if (process_section_renderable($content)): ?>
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
    <?php endif; ?>

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
                        <div class="team-avatar <?= e(display_size_class($content, 'team_avatar')) ?>" aria-hidden="true">
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
                <div class="contact-form-col reveal">
                <form class="contact-form" id="contact-form" action="/api/contact.php" method="post" novalidate data-success="<?= e($contact['form']['success']) ?>" data-error="<?= e($contact['form']['error']) ?>">
                    <input type="hidden" name="lang" value="<?= e($currentLang) ?>">
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
                            rows="3"
                            required
                            placeholder="<?= e($contact['form']['message']['placeholder']) ?>"
                        ></textarea>
                    </div>
                    <p class="form-feedback" id="form-feedback" role="status" aria-live="polite" hidden></p>
                    <button type="submit" class="btn btn-navy"><?= e($contact['form']['submit']) ?></button>
                </form>
                <?php if ($contactHoursRows !== [] && $contactHoursTitle !== ''): ?>
                    <article class="address-card contact-hours-card">
                        <h3><?= e($contactHoursTitle) ?></h3>
                        <dl class="contact-hours-list">
                            <?php foreach ($contactHoursRows as $hoursRow): ?>
                                <div class="contact-hours-row">
                                    <dt><?= e($hoursRow['label']) ?></dt>
                                    <dd><?= e($hoursRow['value']) ?></dd>
                                </div>
                            <?php endforeach; ?>
                        </dl>
                    </article>
                <?php endif; ?>
                </div>

                <div class="contact-info reveal">
                    <div class="contact-info-grid">
                        <?php foreach (contact_info_items($content) as $item): ?>
                            <?php
                            $type = (string) ($item['type'] ?? '');
                            $cardClass = 'address-card';
                            if ($type === 'email') {
                                $cardClass .= ' contact-info-email';
                            }
                            ?>
                            <article class="<?= e($cardClass) ?>">
                                <h3><?= e($item['title'] ?? '') ?></h3>
                                <?php if ($type === 'address'): ?>
                                    <address><?= e($item['value'] ?? '') ?></address>
                                <?php elseif ($type === 'phone' || $type === 'fax'): ?>
                                    <?php $tel = preg_replace('/\s+/', '', (string) ($item['value'] ?? '')); ?>
                                    <p><a href="tel:<?= e($tel) ?>"><?= e($item['value'] ?? '') ?></a></p>
                                <?php elseif ($type === 'email'): ?>
                                    <p><a href="mailto:<?= e($item['value'] ?? '') ?>"><?= e($item['value'] ?? '') ?></a></p>
                                <?php else: ?>
                                    <p><?= e($item['value'] ?? '') ?></p>
                                <?php endif; ?>
                            </article>
                        <?php endforeach; ?>
                    </div>
                    <?php $mapEmbedUrl = contact_turkey_map_embed_url($content); ?>
                    <?php if ($mapEmbedUrl !== ''): ?>
                        <article class="address-card contact-map-card">
                            <iframe
                                class="contact-map-iframe"
                                src="<?= e($mapEmbedUrl) ?>"
                                loading="lazy"
                                title="<?= e((string) ($contact['info_items'][0]['title'] ?? 'Office location')) ?>"
                                referrerpolicy="no-referrer-when-downgrade"
                                allowfullscreen
                            ></iframe>
                        </article>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </section>
    <?php endif; ?>
</main>

<?php require __DIR__ . '/includes/footer.php'; ?>
</body>
</html>
