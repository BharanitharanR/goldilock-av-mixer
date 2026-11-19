from video_audio_mixer.deterministic import default_plan, music_gain_for


def test_near_silent_video_lets_music_carry_the_soundtrack():
    gain, why = music_gain_for(original_mean_db=-52.0, music_mean_db=-20.0, music_peak_db=-3.0)
    assert gain == 2.0          # -20 -> -18 dB mean, peak -1 dB: allowed
    assert "near-silent" in why


def test_video_without_audio_is_treated_like_silence():
    gain, why = music_gain_for(None, -24.0, -8.0)
    assert gain == 6.0 and "no audio track" in why


def test_music_sits_ten_db_under_audible_original():
    gain, _ = music_gain_for(original_mean_db=-20.0, music_mean_db=-16.0, music_peak_db=-2.0)
    assert gain == -14.0        # target -30 dB mean


def test_peaks_are_never_pushed_past_minus_one_db():
    gain, _ = music_gain_for(-60.0, -30.0, -2.0)
    assert gain == 1.0


def test_unmeasured_music_keeps_old_fixed_gain():
    assert default_plan(10.0).music_gain_db == -16.0
