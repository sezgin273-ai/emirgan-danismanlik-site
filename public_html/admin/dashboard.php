<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';
require_once __DIR__ . '/../includes/admin_multilang.php';

admin_require_login();

$adminLang = admin_resolve_lang();
$adminStructural = admin_is_tr_mode($adminLang);
$content = admin_load_lang_file($adminLang);
$csrf = admin_csrf_token();
$backups = list_content_backups_with_labels($adminLang);
$flash = null;

admin_start_session();
if (!empty($_SESSION['admin_flash'])) {
    $flash = $_SESSION['admin_flash'];
    unset($_SESSION['admin_flash']);
}

$serviceIcons = service_icon_names();
$badgeIcons = ['energy', 'realestate', 'trade', 'construction', 'investment'];
$processSteps = $content['process']['steps'] ?? [];
$contactInfoItems = $content['contact']['info_items'] ?? [];
$contactHoursRows = $content['contact']['hours']['rows'] ?? [];
if (!is_array($contactHoursRows)) {
    $contactHoursRows = [];
}
$displayGroups = [
    'header_logo' => 'Üst menü logosu',
    'footer_logo' => 'Footer logosu',
    'team_avatar' => 'Ekip fotoğraf/monogram',
    'service_icon' => 'Hizmet kartı ikonları',
    'hero_emblem' => 'Hero amblem kompozisyonu',
];
$displaySizes = [
    'small' => 'Küçük',
    'medium' => 'Orta',
    'large' => 'Büyük',
];
$contactInfoTypes = [
    'address' => 'Adres',
    'phone' => 'Telefon',
    'fax' => 'Faks',
    'email' => 'E-posta',
    'other' => 'Diğer',
];
$sectionLabels = [
    'hero' => 'Ana Sayfa (Hero)',
    'intro' => 'Kısa Tanıtım',
    'services' => 'Hizmetler',
    'about' => 'Hakkımızda',
    'process' => 'Nasıl Çalışıyoruz',
    'team' => 'Ekibimiz',
    'contact' => 'İletişim',
];
?>
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İçerik Yönetimi — Emirgan Admin</title>
    <link rel="stylesheet" href="/admin/assets/admin.css">
</head>
<body class="<?= $adminStructural ? 'admin-mode-tr' : 'admin-mode-localized' ?>" data-admin-lang="<?= e($adminLang) ?>">
<div class="admin-shell">
    <div class="admin-topbar">
        <h1>İçerik Yönetimi</h1>
        <nav class="admin-lang-switcher" aria-label="Düzenleme dili">
            <?php foreach (SITE_LANGS as $langCode): ?>
                <?php
                $isActive = $langCode === $adminLang;
                $langLabel = strtoupper($langCode);
                $langHref = $langCode === SITE_LANG_DEFAULT
                    ? '/admin/dashboard.php'
                    : '/admin/dashboard.php?admin_lang=' . rawurlencode($langCode);
                ?>
                <a
                    href="<?= e($langHref) ?>"
                    class="admin-lang-switcher__link<?= $isActive ? ' is-active' : '' ?>"
                    hreflang="<?= e($langCode) ?>"
                    lang="<?= e($langCode) ?>"
                    <?= $isActive ? 'aria-current="page"' : '' ?>
                ><?= e($langLabel) ?></a>
            <?php endforeach; ?>
        </nav>
        <form method="post" action="/admin/actions.php">
            <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
            <input type="hidden" name="action" value="logout">
            <button type="submit" class="admin-btn">Çıkış</button>
        </form>
    </div>

    <?php if ($flash): ?>
        <p class="admin-alert admin-alert--<?= e($flash['type'] === 'ok' ? 'ok' : 'error') ?>" role="status">
            <?= e($flash['message']) ?>
        </p>
    <?php endif; ?>

    <nav class="admin-nav" aria-label="Panel bölümleri">
        <a href="#seo">SEO</a>
        <a href="#sections">Bölümler</a>
        <a href="#hero">Hero</a>
        <a href="#intro">Tanıtım</a>
        <a href="#about">Hakkımızda</a>
        <a href="#process">Süreç</a>
        <a href="#services">Hizmetler</a>
        <a href="#team">Ekip</a>
        <a href="#contact">İletişim</a>
        <a href="#kvkk">KVKK</a>
        <a href="#media">Görseller</a>
        <a href="#display">Boyutlar</a>
        <a href="#backups">Yedekler</a>
        <a href="/" target="_blank" rel="noopener">Siteyi aç</a>
    </nav>

    <form method="post" action="/admin/actions.php" class="admin-form" id="content-form">
        <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
        <input type="hidden" name="action" value="save_content">
        <input type="hidden" name="admin_lang" value="<?= e($adminLang) ?>">

        <section class="admin-card" id="seo">
            <h2>SEO ve Site</h2>
            <div class="admin-grid-2">
                <div>
                    <label for="site-title">Site başlığı</label>
                    <input type="text" id="site-title" name="content[site][title]" value="<?= e($content['site']['title']) ?>">
                </div>
                <div>
                    <label for="site-lang">Dil kodu</label>
                    <input type="text" id="site-lang" name="content[site][lang]" value="<?= e($content['site']['lang']) ?>"<?= $adminStructural ? '' : ' readonly class="admin-readonly"' ?>>
                </div>
            </div>
            <label for="meta-description">Meta açıklama</label>
            <textarea id="meta-description" name="content[site][meta][description]"><?= e($content['site']['meta']['description'] ?? '') ?></textarea>
            <label for="og-title">OG başlık</label>
            <input type="text" id="og-title" name="content[site][meta][og_title]" value="<?= e($content['site']['meta']['og_title'] ?? '') ?>">
            <label for="og-description">OG açıklama</label>
            <textarea id="og-description" name="content[site][meta][og_description]"><?= e($content['site']['meta']['og_description'] ?? '') ?></textarea>
        </section>

        <section class="admin-card<?= $adminStructural ? '' : ' admin-card--readonly' ?>" id="sections">
            <h2>Bölüm Görünürlüğü</h2>
            <p class="admin-muted">Kapalı bölümler ön yüzde ve menüde görünmez.</p>
            <?php foreach ($sectionLabels as $sid => $label): ?>
            <label class="admin-check" data-admin-structural>
                <input type="checkbox" name="content[site][sections][<?= e($sid) ?>][visible]" value="1"
                    <?= section_visible($content, $sid) ? 'checked' : '' ?><?= $adminStructural ? '' : ' disabled' ?>>
                    <?= e($label) ?>
                </label>
            <?php endforeach; ?>
        </section>

        <section class="admin-card" id="hero">
            <h2>Hero</h2>
            <label for="hero-company">Şirket adı</label>
            <input type="text" id="hero-company" name="content[hero][company]" value="<?= e($content['hero']['company']) ?>">
            <label for="hero-tagline">Slogan</label>
            <input type="text" id="hero-tagline" name="content[hero][tagline]" value="<?= e($content['hero']['tagline']) ?>">
            <label for="hero-description">Açıklama</label>
            <textarea id="hero-description" name="content[hero][description]"><?= e($content['hero']['description']) ?></textarea>
            <label class="admin-check" data-admin-structural>
                <input type="hidden" name="content[hero][watermark_enabled]" value="0">
                <input type="checkbox" name="content[hero][watermark_enabled]" value="1"
                    <?= hero_watermark_enabled($content) ? 'checked' : '' ?><?= $adminStructural ? '' : ' disabled' ?>>
                Arka plan watermark (amblem) göster
            </label>
        </section>

        <section class="admin-card" id="intro">
            <h2>Kısa Tanıtım</h2>
            <label for="intro-title">Başlık</label>
            <input type="text" id="intro-title" name="content[intro][title]" value="<?= e($content['intro']['title']) ?>">
            <label for="intro-text">Metin</label>
            <textarea id="intro-text" name="content[intro][text]"><?= e($content['intro']['text']) ?></textarea>
            <h3>Rozetler</h3>
            <input type="hidden" name="content[intro][badges_present]" value="1">
            <div id="badges-list" data-sortable-prefix="content[intro][badges]" data-label-prefix="Rozet" data-allow-empty>
                <?php foreach ($content['intro']['badges'] as $i => $badge): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Rozet <?= $i + 1 ?></strong>
                            <button type="button" class="admin-btn admin-btn--danger" data-remove-item>Sil</button>
                        </div>
                        <div class="admin-grid-2">
                            <div>
                                <label>İkon</label>
                                <select name="content[intro][badges][<?= $i ?>][icon]">
                                    <?php foreach ($badgeIcons as $icon): ?>
                                        <option value="<?= e($icon) ?>" <?= $badge['icon'] === $icon ? 'selected' : '' ?>><?= e($icon) ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </div>
                            <div>
                                <label>Etiket</label>
                                <input type="text" name="content[intro][badges][<?= $i ?>][label]" value="<?= e($badge['label']) ?>">
                            </div>
                        </div>
                    </div>
                <?php endforeach; ?>
            </div>
        </section>

        <section class="admin-card" id="about">
            <h2>Hakkımızda</h2>
            <label for="about-title">Bölüm başlığı</label>
            <input type="text" id="about-title" name="content[about][title]" value="<?= e($content['about']['title']) ?>">
            <label for="about-heading">Alt başlık</label>
            <input type="text" id="about-heading" name="content[about][heading]" value="<?= e($content['about']['heading']) ?>">
            <input type="hidden" name="content[about][paragraphs_present]" value="1">
            <?php foreach ($content['about']['paragraphs'] as $i => $paragraph): ?>
                <label>Paragraf <?= $i + 1 ?></label>
                <textarea name="content[about][paragraphs][<?= $i ?>]"><?= e($paragraph) ?></textarea>
            <?php endforeach; ?>
            <h3>Vizyon</h3>
            <input type="text" name="content[vision][title]" value="<?= e($content['vision']['title']) ?>">
            <textarea name="content[vision][text]"><?= e($content['vision']['text']) ?></textarea>
            <h3>Misyon</h3>
            <input type="text" name="content[mission][title]" value="<?= e($content['mission']['title']) ?>">
            <textarea name="content[mission][text]"><?= e($content['mission']['text']) ?></textarea>
        </section>

        <section class="admin-card" id="process">
            <h2>Nasıl Çalışıyoruz</h2>
            <label for="process-title">Bölüm başlığı</label>
            <input type="text" id="process-title" name="content[process][title]" value="<?= e($content['process']['title'] ?? '') ?>">
            <input type="hidden" name="content[process][steps_present]" value="1">
            <div id="process-list" data-sortable-prefix="content[process][steps]" data-label-prefix="Adım">
                <?php foreach ($processSteps as $i => $step): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Adım <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button type="button" class="admin-btn admin-btn--danger" data-delete-process-step data-step-index="<?= $i ?>">Sil</button>
                            </div>
                        </div>
                        <label>Başlık</label>
                        <input type="text" name="content[process][steps][<?= $i ?>][title]" value="<?= e($step['title']) ?>">
                        <label>Açıklama</label>
                        <textarea name="content[process][steps][<?= $i ?>][description]"><?= e($step['description']) ?></textarea>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-process>Adım Ekle</button>
        </section>

        <section class="admin-card" id="services">
            <h2>Hizmetler</h2>
            <label for="services-title">Bölüm başlığı</label>
            <input type="text" id="services-title" name="content[services][title]" value="<?= e($content['services']['title']) ?>">
            <input type="hidden" name="content[services][items_present]" value="1">
            <div id="services-list" data-sortable-prefix="content[services][items]" data-label-prefix="Kart">
                <?php foreach ($content['services']['items'] as $i => $service): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Kart <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button type="button" class="admin-btn admin-btn--danger" data-remove-item>Sil</button>
                            </div>
                        </div>
                        <label>İkon</label>
                        <select name="content[services][items][<?= $i ?>][icon]">
                            <?php foreach ($serviceIcons as $icon): ?>
                                <option value="<?= e($icon) ?>" <?= $service['icon'] === $icon ? 'selected' : '' ?>><?= e($icon) ?></option>
                            <?php endforeach; ?>
                        </select>
                        <label>Başlık</label>
                        <input type="text" name="content[services][items][<?= $i ?>][title]" value="<?= e($service['title']) ?>">
                        <label>Açıklama</label>
                        <textarea name="content[services][items][<?= $i ?>][description]"><?= e($service['description']) ?></textarea>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-service>Hizmet Ekle</button>
        </section>

        <section class="admin-card" id="team">
            <h2>Ekibimiz</h2>
            <label for="team-title">Bölüm başlığı</label>
            <input type="text" id="team-title" name="content[team][title]" value="<?= e($content['team']['title']) ?>">
            <label for="team-intro">Giriş metni</label>
            <textarea id="team-intro" name="content[team][intro]"><?= e($content['team']['intro']) ?></textarea>
            <input type="hidden" name="content[team][members_present]" value="1">
            <div id="team-list" data-sortable-prefix="content[team][members]" data-label-prefix="Üye">
                <?php foreach ($content['team']['members'] as $i => $member): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Üye <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button type="button" class="admin-btn admin-btn--danger" data-delete-team-member data-member-index="<?= $i ?>">Sil</button>
                            </div>
                        </div>
                        <input type="hidden" name="content[team][members][<?= $i ?>][photo]" value="<?= e($member['photo'] ?? '') ?>">
                        <label>Ad Soyad</label>
                        <input type="text" name="content[team][members][<?= $i ?>][name]" value="<?= e($member['name']) ?>">
                        <label>Ünvan</label>
                        <input type="text" name="content[team][members][<?= $i ?>][title]" value="<?= e($member['title']) ?>">
                        <label>Açıklama</label>
                        <textarea name="content[team][members][<?= $i ?>][description]"><?= e($member['description']) ?></textarea>
                        <?php if (!empty($member['photo'])): ?>
                            <img src="<?= e($member['photo']) ?>" alt="" class="admin-photo-preview">
                            <button
                                type="button"
                                class="admin-btn admin-btn--danger"
                                data-remove-team-photo
                                data-member-index="<?= $i ?>"
                            >Fotoğrafı Kaldır</button>
                        <?php endif; ?>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-team>Üye Ekle</button>
        </section>

        <section class="admin-card" id="contact">
            <h2>İletişim</h2>
            <label for="contact-title">Bölüm başlığı</label>
            <input type="text" id="contact-title" name="content[contact][title]" value="<?= e($content['contact']['title']) ?>">
            <label for="contact-heading">Alt başlık</label>
            <input type="text" id="contact-heading" name="content[contact][heading]" value="<?= e($content['contact']['heading']) ?>">
            <label for="contact-email">E-posta (eski anahtar)</label>
            <input type="email" id="contact-email" name="content[contact][email]" value="<?= e($content['contact']['email']) ?>"<?= $adminStructural ? '' : ' readonly class="admin-readonly"' ?>>
            <h3>İletişim bilgileri (ön yüz)</h3>
            <input type="hidden" name="content[contact][info_items_present]" value="1">
            <div id="contact-info-list" data-sortable-prefix="content[contact][info_items]" data-label-prefix="Bilgi">
                <?php foreach ($contactInfoItems as $i => $infoItem): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Bilgi <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button
                                    type="button"
                                    class="admin-btn admin-btn--danger"
                                    data-delete-contact-info
                                    data-info-index="<?= $i ?>"
                                >Sil</button>
                            </div>
                        </div>
                        <div class="admin-grid-2">
                            <div>
                                <label>Tip</label>
                                <select name="content[contact][info_items][<?= $i ?>][type]">
                                    <?php foreach ($contactInfoTypes as $typeKey => $typeLabel): ?>
                                        <option value="<?= e($typeKey) ?>" <?= ($infoItem['type'] ?? '') === $typeKey ? 'selected' : '' ?>><?= e($typeLabel) ?></option>
                                    <?php endforeach; ?>
                                </select>
                            </div>
                            <div>
                                <label>Başlık</label>
                                <input type="text" name="content[contact][info_items][<?= $i ?>][title]" value="<?= e($infoItem['title'] ?? '') ?>">
                            </div>
                        </div>
                        <label>Değer</label>
                        <textarea name="content[contact][info_items][<?= $i ?>][value]"><?= e($infoItem['value'] ?? '') ?></textarea>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-contact-info>İletişim Bilgisi Ekle</button>
            <input type="hidden" name="content[contact][addresses_present]" value="1">
            <?php foreach ($content['contact']['addresses'] as $i => $address): ?>
                <h3>Adres <?= $i + 1 ?></h3>
                <input type="text" name="content[contact][addresses][<?= $i ?>][label]" value="<?= e($address['label']) ?>">
                <textarea name="content[contact][addresses][<?= $i ?>][text]"><?= e($address['text']) ?></textarea>
            <?php endforeach; ?>
            <h3>Form metinleri</h3>
            <?php foreach (['name', 'email', 'phone', 'subject', 'message'] as $field): ?>
                <label><?= e($content['contact']['form'][$field]['label']) ?></label>
                <input type="text" name="content[contact][form][<?= $field ?>][label]" value="<?= e($content['contact']['form'][$field]['label']) ?>">
                <input type="text" name="content[contact][form][<?= $field ?>][placeholder]" value="<?= e($content['contact']['form'][$field]['placeholder']) ?>">
            <?php endforeach; ?>
            <label>Gönder butonu</label>
            <input type="text" name="content[contact][form][submit]" value="<?= e($content['contact']['form']['submit']) ?>">
            <label>Başarı mesajı</label>
            <input type="text" name="content[contact][form][success]" value="<?= e($content['contact']['form']['success']) ?>">
            <label>Hata mesajı</label>
            <input type="text" name="content[contact][form][error]" value="<?= e($content['contact']['form']['error']) ?>">
            <h3<?= $adminStructural ? ' data-admin-structural' : '' ?>>Çalışma Saatleri</h3>
            <input type="hidden" name="content[contact][hours_present]" value="1">
            <label for="contact-hours-title">Kart başlığı</label>
            <input type="text" id="contact-hours-title" name="content[contact][hours][title]" value="<?= e($content['contact']['hours']['title'] ?? '') ?>">
            <div id="contact-hours-list" data-sortable-prefix="content[contact][hours][rows]" data-label-prefix="Satır">
                <?php foreach ($contactHoursRows as $i => $hoursRow): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Satır <?= $i + 1 ?></strong>
                            <div class="admin-actions-row"<?= $adminStructural ? ' data-admin-structural' : '' ?>>
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button
                                    type="button"
                                    class="admin-btn admin-btn--danger"
                                    data-delete-contact-hours
                                    data-hours-index="<?= $i ?>"
                                >Sil</button>
                            </div>
                        </div>
                        <div class="admin-grid-2">
                            <div>
                                <label>Etiket</label>
                                <input type="text" name="content[contact][hours][rows][<?= $i ?>][label]" value="<?= e($hoursRow['label'] ?? '') ?>">
                            </div>
                            <div>
                                <label>Değer</label>
                                <input type="text" name="content[contact][hours][rows][<?= $i ?>][value]" value="<?= e($hoursRow['value'] ?? '') ?>">
                            </div>
                        </div>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-contact-hours<?= $adminStructural ? ' data-admin-structural' : '' ?>>Satır Ekle</button>
        </section>

        <section class="admin-card" id="kvkk">
            <h2>KVKK</h2>
            <label for="kvkk-title">Sayfa başlığı</label>
            <input type="text" id="kvkk-title" name="content[kvkk][title]" value="<?= e($content['kvkk']['title']) ?>">
            <label for="kvkk-intro">Giriş</label>
            <textarea id="kvkk-intro" name="content[kvkk][intro]"><?= e($content['kvkk']['intro']) ?></textarea>
            <input type="hidden" name="content[kvkk][sections_present]" value="1">
            <?php foreach ($content['kvkk']['sections'] as $i => $section): ?>
                <h3>Bölüm <?= $i + 1 ?></h3>
                <input type="text" name="content[kvkk][sections][<?= $i ?>][heading]" value="<?= e($section['heading']) ?>">
                <?php foreach ($section['paragraphs'] as $j => $paragraph): ?>
                    <textarea name="content[kvkk][sections][<?= $i ?>][paragraphs][<?= $j ?>]"><?= e($paragraph) ?></textarea>
                <?php endforeach; ?>
            <?php endforeach; ?>
            <label for="kvkk-note">Not</label>
            <textarea id="kvkk-note" name="content[kvkk][note]"><?= e($content['kvkk']['note'] ?? '') ?></textarea>
        </section>

        <section class="admin-card<?= $adminStructural ? '' : ' admin-card--readonly' ?>" id="display">
            <h2>Görsel Boyutları</h2>
            <?php if (!$adminStructural): ?>
                <p class="admin-muted">Görsel boyutları yalnızca TR modunda düzenlenebilir.</p>
            <?php endif; ?>
            <p class="admin-muted">Varsayılan Orta, bugünkü ölçülerle aynıdır.</p>
            <?php foreach ($displayGroups as $groupKey => $groupLabel): ?>
                <label for="display-<?= e($groupKey) ?>"><?= e($groupLabel) ?></label>
                <select id="display-<?= e($groupKey) ?>" name="content[display][<?= e($groupKey) ?>]"<?= $adminStructural ? '' : ' disabled' ?>>
                    <?php foreach ($displaySizes as $sizeKey => $sizeLabel): ?>
                        <option value="<?= e($sizeKey) ?>" <?= display_size_value($content, $groupKey) === $sizeKey ? 'selected' : '' ?>><?= e($sizeLabel) ?></option>
                    <?php endforeach; ?>
                </select>
            <?php endforeach; ?>
        </section>

        <section class="admin-card" id="footer">
            <h2>Footer ve UI</h2>
            <label>Footer hızlı bağlantılar başlığı</label>
            <input type="text" name="content[footer][quick_links_title]" value="<?= e($content['footer']['quick_links_title']) ?>">
            <label>Menü CTA</label>
            <input type="text" name="content[navigation][cta][label]" value="<?= e($content['navigation']['cta']['label']) ?>">
            <?php foreach ($content['navigation']['items'] as $i => $item): ?>
                <label>Menü: <?= e($item['id']) ?></label>
                <input type="text" name="content[navigation][items][<?= $i ?>][label]" value="<?= e($item['label']) ?>">
            <?php endforeach; ?>
        </section>

        <div class="admin-sticky-save">
            <button type="submit" class="admin-btn admin-btn--primary">Tüm İçeriği Kaydet</button>
        </div>
    </form>

    <section class="admin-card<?= $adminStructural ? '' : ' admin-card--readonly' ?>" id="media">
        <h2>Görsel Yükleme</h2>
        <?php if ($adminStructural): ?>
        <p class="admin-muted">Logo/amblem değişiminde mevcut dosyaların üzerine yazılmaz; yeni dosya yolu content.json'a kaydedilir.</p>

        <h3>Ekip fotoğrafı</h3>
        <?php foreach ($content['team']['members'] as $i => $member): ?>
            <div class="admin-list-item">
                <strong><?= e($member['name']) ?></strong>
                <form method="post" action="/admin/actions.php" enctype="multipart/form-data" class="admin-form">
                    <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                    <input type="hidden" name="action" value="upload_team_photo">
                    <input type="hidden" name="admin_lang" value="<?= e($adminLang) ?>">
                    <input type="hidden" name="member_index" value="<?= $i ?>">
                    <input type="file" name="photo" accept="image/png,image/jpeg,image/webp" required>
                    <div class="admin-actions-row">
                        <button type="submit" class="admin-btn admin-btn--gold">Fotoğraf Yükle</button>
                        <?php if (!empty($member['photo'])): ?>
                            <button
                                type="button"
                                class="admin-btn admin-btn--danger"
                                data-remove-team-photo
                                data-member-index="<?= $i ?>"
                            >Fotoğrafı Kaldır</button>
                        <?php endif; ?>
                    </div>
                </form>
            </div>
        <?php endforeach; ?>

        <h3>Marka varlıkları</h3>
        <?php
        $assetFields = [
            'logo_light' => 'Logo (açık zemin)',
            'logo_dark' => 'Logo (koyu zemin)',
            'emblem' => 'Amblem (hero)',
            'favicon' => 'Favicon',
            'apple_touch_icon' => 'Apple Touch Icon',
        ];
        foreach ($assetFields as $key => $label):
            $path = $content['site']['assets'][$key] ?? '';
        ?>
            <div class="admin-list-item">
                <strong><?= e($label) ?></strong>
                <p class="admin-muted">Mevcut: <?= e($path) ?></p>
                <form method="post" action="/admin/actions.php" enctype="multipart/form-data" class="admin-form">
                    <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                    <input type="hidden" name="action" value="upload_asset">
                    <input type="hidden" name="admin_lang" value="<?= e($adminLang) ?>">
                    <input type="hidden" name="asset_key" value="<?= e($key) ?>">
                    <input type="file" name="asset_file" accept="image/png,image/jpeg,image/webp" required>
                    <button type="submit" class="admin-btn">Yükle</button>
                </form>
            </div>
        <?php endforeach; ?>
        <?php else: ?>
            <p class="admin-muted">Görsel yolları yalnızca TR modunda düzenlenebilir.</p>
        <?php endif; ?>
    </section>

    <section class="admin-card" id="backups">
        <h2>Yedekler (<?= e(strtoupper($adminLang)) ?>)</h2>
        <p class="admin-muted">Her kayıttan önce otomatik yedek alınır (son 20).</p>
        <?php if ($backups === []): ?>
            <p class="admin-muted">Henüz yedek yok.</p>
        <?php else: ?>
            <ul class="admin-backup-list">
                <?php foreach ($backups as $backup): ?>
                    <li class="admin-backup-item">
                        <div class="admin-backup-item__meta">
                            <?php if ($backup['is_latest']): ?>
                                <span class="admin-badge admin-badge--gold">En güncel</span>
                            <?php endif; ?>
                            <span><?= e($backup['name']) ?> — <?= date('d.m.Y H:i', $backup['mtime']) ?></span>
                            <?php if (!empty($backup['label'])): ?>
                                <span class="admin-muted">(<?= e($backup['label']) ?>)</span>
                            <?php endif; ?>
                        </div>
                        <div class="admin-backup-item__actions">
                            <form method="post" action="/admin/actions.php" class="admin-form admin-form--inline">
                                <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                                <input type="hidden" name="action" value="label_backup">
                                <input type="hidden" name="admin_lang" value="<?= e($adminLang) ?>">
                                <input type="hidden" name="backup_name" value="<?= e($backup['name']) ?>">
                                <input type="text" name="backup_label" value="<?= e($backup['label']) ?>" maxlength="50" placeholder="Etiket">
                                <button type="submit" class="admin-btn">Etiket Kaydet</button>
                            </form>
                            <form method="post" action="/admin/actions.php" class="admin-form admin-form--inline">
                                <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                                <input type="hidden" name="action" value="restore_backup">
                                <input type="hidden" name="admin_lang" value="<?= e($adminLang) ?>">
                                <input type="hidden" name="backup_name" value="<?= e($backup['name']) ?>">
                                <button type="submit" class="admin-btn">Geri Yükle</button>
                            </form>
                            <button
                                type="button"
                                class="admin-btn admin-btn--danger"
                                data-delete-backup
                                data-backup-name="<?= e($backup['name']) ?>"
                            >Sil</button>
                        </div>
                    </li>
                <?php endforeach; ?>
            </ul>
        <?php endif; ?>
    </section>
</div>

<template id="contact-info-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni bilgi</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
                <button type="button" class="admin-btn admin-btn--danger" data-delete-contact-info data-info-index="__INDEX__">Sil</button>
            </div>
        </div>
        <div class="admin-grid-2">
            <div>
                <label>Tip</label>
                <select name="content[contact][info_items][__INDEX__][type]">
                    <?php foreach ($contactInfoTypes as $typeKey => $typeLabel): ?>
                        <option value="<?= e($typeKey) ?>"><?= e($typeLabel) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div>
                <label>Başlık</label>
                <input type="text" name="content[contact][info_items][__INDEX__][title]" placeholder="Başlık">
            </div>
        </div>
        <label>Değer</label>
        <textarea name="content[contact][info_items][__INDEX__][value]" placeholder="Değer"></textarea>
    </div>
</template>

<template id="contact-hours-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni satır</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
                <button type="button" class="admin-btn admin-btn--danger" data-delete-contact-hours data-hours-index="__INDEX__">Sil</button>
            </div>
        </div>
        <div class="admin-grid-2">
            <div>
                <label>Etiket</label>
                <input type="text" name="content[contact][hours][rows][__INDEX__][label]" placeholder="Etiket">
            </div>
            <div>
                <label>Değer</label>
                <input type="text" name="content[contact][hours][rows][__INDEX__][value]" placeholder="Değer">
            </div>
        </div>
    </div>
</template>

<template id="service-item-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni kart</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
                <button type="button" class="admin-btn admin-btn--danger" data-remove-item>Sil</button>
            </div>
        </div>
        <select name="content[services][items][__INDEX__][icon]">
            <?php foreach ($serviceIcons as $icon): ?>
                <option value="<?= e($icon) ?>"><?= e($icon) ?></option>
            <?php endforeach; ?>
        </select>
        <input type="text" name="content[services][items][__INDEX__][title]" placeholder="Başlık">
        <textarea name="content[services][items][__INDEX__][description]" placeholder="Açıklama"></textarea>
    </div>
</template>

<template id="process-item-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni adım</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
                <button type="button" class="admin-btn admin-btn--danger" data-delete-process-step data-step-index="__INDEX__">Sil</button>
            </div>
        </div>
        <input type="text" name="content[process][steps][__INDEX__][title]" placeholder="Adım başlığı">
        <textarea name="content[process][steps][__INDEX__][description]" placeholder="Adım açıklaması"></textarea>
    </div>
</template>

<template id="team-item-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni üye</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
            </div>
        </div>
        <input type="hidden" name="content[team][members][__INDEX__][photo]" value="">
        <input type="text" name="content[team][members][__INDEX__][name]" placeholder="Ad Soyad">
        <input type="text" name="content[team][members][__INDEX__][title]" placeholder="Ünvan">
        <textarea name="content[team][members][__INDEX__][description]" placeholder="Açıklama"></textarea>
    </div>
</template>

<script src="/admin/assets/admin.js" defer></script>
</body>
</html>
