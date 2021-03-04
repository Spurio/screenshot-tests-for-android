/*
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.facebook.testing.screenshot.sample

import android.app.Activity
import android.view.View
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.openActionBarOverflowOrOptionsMenu
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.rule.ActivityTestRule
import androidx.test.rule.GrantPermissionRule
import io.spur.testing.screenshot.Screenshot
import org.hamcrest.core.AllOf.allOf
import org.junit.Rule
import org.junit.Test

class MainActivityTest {
  @get:Rule
  var activityTestRule = ActivityTestRule<MainActivity>(MainActivity::class.java, false, false)
  @get:Rule
  val permissionRule: GrantPermissionRule = GrantPermissionRule.grant(
      android.Manifest.permission.WRITE_EXTERNAL_STORAGE
  )

  fun makeScreenshot(activity: Activity) {
    Screenshot.snapActivity(activity).record()
  }

  @Test
  fun testScreenshotEntireActivity() {
    val activity = activityTestRule.launchActivity(null)
    makeScreenshot(activity)
  }

  @Test
  fun mainActivityTestSettingsOpen() {
    val activity = activityTestRule.launchActivity(null)
    val floatingActionButton = onView(allOf<View>(withId(R.id.fab), isDisplayed()))
    floatingActionButton.perform(click())

    openActionBarOverflowOrOptionsMenu(activity)
    makeScreenshot(activity)
  }

//  @Test
//  fun mainActivityTestFabWithEspresso() {
//    activityTestRule.launchActivity(null)
//    onView(withId(R.id.fab)).perform(screenshot("fab"))
//  }

  @Test
  fun errorTextShouldBeRed() {
    val intent = MainActivity.intent(MainActivity.Status.ERROR)
    val activity = activityTestRule.launchActivity(null)

    makeScreenshot(activity)

  }

  @Test
  fun warningTextShouldBeYellow() {
    val intent = MainActivity.intent(MainActivity.Status.WARNING)
    val activity = activityTestRule.launchActivity(intent)

    makeScreenshot(activity)

  }

  @Test
  fun okTextShouldBeGreen() {
    val intent = MainActivity.intent(MainActivity.Status.OK)
    val activity = activityTestRule.launchActivity(null)

    makeScreenshot(activity)

  }

  @Test
  fun testScreenshotEntireActivityWithoutAccessibilityMetadata() {
    val activity = activityTestRule.launchActivity(null)
    makeScreenshot(activity)

  }
}
